"""Enhanced request queue for Telegram API rate limiting with adaptive throttling."""

import asyncio
import logging
import time
from typing import Callable, Any, Optional
from collections import deque

logger = logging.getLogger(__name__)

# Module-level singleton for global queue (shared within one worker process)
_global_queue_instance: Optional['TelegramRequestQueue'] = None
_queue_lock = asyncio.Lock()


def get_global_queue(max_concurrent: int = 5, delay_ms: int = 150, adaptive: bool = True) -> 'TelegramRequestQueue':
    """Get or create global queue instance (singleton per worker process).
    
    This ensures all TelegramServiceEnhanced instances in the same worker
    share the same queue, preventing duplicate rate limiting.
    """
    global _global_queue_instance
    
    if _global_queue_instance is None:
        _global_queue_instance = TelegramRequestQueue(
            max_concurrent=max_concurrent,
            delay_ms=delay_ms,
            adaptive=adaptive
        )
        logger.info("Created global TelegramRequestQueue singleton")
    
    return _global_queue_instance


class TelegramRequestQueue:
    """Manages request queue for Telegram API with adaptive rate limiting.
    
    Features:
    - Single queue per worker process (prevents 429 errors within worker)
    - Adaptive throttling based on 429 errors
    - Concurrent request limiting via semaphore
    - Dynamic delay adjustment
    """
    
    def __init__(self, max_concurrent: int = 5, delay_ms: int = 150, adaptive: bool = True):
        """Initialize request queue.
        
        Args:
            max_concurrent: Maximum concurrent API requests per worker
            delay_ms: Initial delay between requests in milliseconds
            adaptive: Enable adaptive rate limiting (adjusts delay based on 429 errors)
        """
        self.max_concurrent = max_concurrent
        self.adaptive = adaptive
        self.base_delay = delay_ms / 1000.0  # Convert to seconds
        self.current_delay = delay_ms / 1000.0
        
        # Queue and semaphore for this worker
        self.queue: asyncio.Queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.last_request_time = 0
        
        # Rate limiting state
        self.rate_limit_active = False
        self.rate_limit_until = 0
        self.consecutive_429_count = 0
        self.request_times = deque(maxlen=100)  # Track last 100 requests
        self.lock = asyncio.Lock()
        
        # Background task for processing queue
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"TelegramRequestQueue initialized: max_concurrent={max_concurrent}, "
            f"initial_delay={delay_ms}ms, adaptive={adaptive}"
        )
    
    def _start_processor(self):
        """Start background task to process queue."""
        if not self._running:
            self._running = True
            self._processor_task = asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Process queued requests one by one with rate limiting."""
        while self._running:
            try:
                # Wait for request in queue (with timeout to check running flag)
                try:
                    request_data = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                
                if request_data is None:  # Shutdown signal
                    break
                
                func, args, kwargs, future = request_data
                
                # Wait for rate limit to expire if active
                if self.rate_limit_active:
                    wait_time = self.rate_limit_until - time.time()
                    if wait_time > 0:
                        logger.warning(f"Rate limit active, waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                        self.rate_limit_active = False
                
                # Wait for delay since last request
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                if time_since_last < self.current_delay:
                    await asyncio.sleep(self.current_delay - time_since_last)
                
                # Acquire semaphore to limit concurrent requests
                async with self.semaphore:
                    self.last_request_time = time.time()
                    self.request_times.append(time.time())
                    
                    try:
                        # Execute the function
                        result = await func(*args, **kwargs)
                        future.set_result(result)
                        
                        # On success, gradually reduce delay if adaptive
                        await self._on_success()
                    except Exception as e:
                        future.set_exception(e)
                        # Check if this is a 429 error
                        if hasattr(e, 'status') and e.status == 429:
                            await self._handle_rate_limit()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                if 'future' in locals() and not future.done():
                    future.set_exception(e)
    
    async def _on_success(self):
        """Handle successful request - gradually reduce delay if adaptive."""
        if not self.adaptive:
            return
        
        async with self.lock:
            if self.consecutive_429_count > 0:
                # Gradually reduce consecutive count on success
                self.consecutive_429_count = max(0, self.consecutive_429_count - 1)
            
            # Gradually reduce delay after successful requests (but not below base)
            if self.consecutive_429_count == 0 and self.current_delay > self.base_delay:
                self.current_delay = max(self.base_delay, self.current_delay * 0.98)
    
    async def _handle_rate_limit(self):
        """Handle 429 rate limit error with adaptive throttling."""
        async with self.lock:
            self.consecutive_429_count += 1
            
            # Increase delay exponentially based on consecutive 429 errors
            multiplier = min(2.0 ** self.consecutive_429_count, 10.0)
            self.current_delay = self.base_delay * multiplier
            
            # Activate rate limit for a period
            rate_limit_duration = min(self.consecutive_429_count * 5, 60)  # Max 60s
            self.rate_limit_active = True
            self.rate_limit_until = time.time() + rate_limit_duration
            
            logger.warning(
                f"Rate limit detected (429). Adaptive throttling: "
                f"delay={self.current_delay*1000:.0f}ms, "
                f"consecutive_429={self.consecutive_429_count}, "
                f"rate_limit_duration={rate_limit_duration}s"
            )
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through queue with rate limiting.
        
        All requests in the same worker process go through the same queue,
        preventing 429 errors from concurrent requests within the worker.
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of function execution
        """
        # Start processor if not running
        if not self._running:
            self._start_processor()
        
        # Create future for result
        future = asyncio.Future()
        
        # Add request to queue
        await self.queue.put((func, args, kwargs, future))
        
        # Wait for result
        return await future
    
    async def shutdown(self):
        """Shutdown queue processor gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        if self._processor_task:
            try:
                # Signal shutdown by putting None in queue
                await self.queue.put(None)
            except Exception:
                pass  # Queue might be closed or full
            
            try:
                # Wait for processor to finish (with timeout)
                await asyncio.wait_for(self._processor_task, timeout=5.0)
            except asyncio.TimeoutError:
                # Force cancel if it doesn't finish in time
                self._processor_task.cancel()
                try:
                    await self._processor_task
                except asyncio.CancelledError:
                    pass
            except Exception:
                pass  # Task might already be done
