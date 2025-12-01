"""Performance tracking utilities."""
import time
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track performance metrics for operations."""
    
    def __init__(self, operation_name: str):
        """Initialize performance tracker."""
        self.operation_name = operation_name
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self) -> None:
        """Start tracking."""
        self.start_time = time.time()
    
    def stop(self) -> float:
        """
        Stop tracking and return elapsed time in milliseconds.
        
        Returns:
            Elapsed time in milliseconds
        """
        if self.start_time is None:
            raise ValueError("Tracker not started")
        self.end_time = time.time()
        return (self.end_time - self.start_time) * 1000
    
    def elapsed_ms(self) -> float:
        """
        Get elapsed time in milliseconds without stopping.
        
        Returns:
            Elapsed time in milliseconds
        """
        if self.start_time is None:
            return 0.0
        return (time.time() - self.start_time) * 1000
    
    def elapsed_seconds(self) -> float:
        """
        Get elapsed time in seconds without stopping.
        
        Returns:
            Elapsed time in seconds
        """
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


@asynccontextmanager
async def track_performance(operation_name: str):
    """
    Context manager for tracking performance.
    
    Usage:
        async with track_performance("operation_name") as tracker:
            # Do work
            result = await some_operation()
        # tracker.elapsed_ms() available after context
    """
    tracker = PerformanceTracker(operation_name)
    tracker.start()
    try:
        yield tracker
    finally:
        elapsed = tracker.stop()
        logger.debug(f"{operation_name} took {elapsed:.2f}ms")


async def measure_async(
    func: Callable,
    *args,
    operation_name: Optional[str] = None,
    **kwargs
) -> tuple[Any, float]:
    """
    Measure execution time of an async function.
    
    Args:
        func: Async function to measure
        *args: Positional arguments for function
        operation_name: Name for logging (defaults to function name)
        **kwargs: Keyword arguments for function
        
    Returns:
        Tuple of (result, elapsed_time_ms)
    """
    name = operation_name or func.__name__
    start = time.time()
    result = await func(*args, **kwargs)
    elapsed_ms = (time.time() - start) * 1000
    logger.debug(f"{name} took {elapsed_ms:.2f}ms")
    return result, elapsed_ms

