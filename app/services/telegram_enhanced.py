import aiohttp
import asyncio
import logging
import time
import random
from typing import Optional, Tuple, Dict, Any
from app.config import settings
from app.services.telegram_queue import TelegramRequestQueue

logger = logging.getLogger(__name__)

# Create a separate logger for detailed API interactions
api_logger = logging.getLogger(f"{__name__}.api")
api_logger.setLevel(logging.DEBUG)


class TelegramAPIError(Exception):
    """Non-retriable Telegram API error with original status and description."""
    def __init__(self, status: int, description: str):
        self.status = status
        self.description = description
        super().__init__(f"{status}: {description}")


class TelegramServiceEnhanced:
    """Enhanced service for interacting with Telegram Bot API with adaptive retry and rate limiting."""
    
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.api_base_url = settings.telegram_api_base_url
        self.download_base_url = settings.telegram_download_base_url
        self._session: Optional[aiohttp.ClientSession] = None
        
        # API statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_bytes_downloaded': 0,
            'total_download_time_ms': 0,
            'errors_by_type': {},
            'rate_limited_requests': 0,
            'retry_attempts': 0,
        }
        
        # Rate limiting and retry configuration
        self.rate_limit_detected = False
        self.rate_limit_reset_time = 0
        self.base_retry_delay = 1.0  # Base delay in seconds
        self.max_retry_delay = 60.0  # Maximum delay in seconds
        self.max_retries = 3
        
        # Use global queue singleton (shared within worker process)
        from app.services.telegram_queue import get_global_queue
        self.request_queue = get_global_queue(
            max_concurrent=settings.telegram_max_concurrent_requests,
            delay_ms=settings.telegram_request_delay_ms,
            adaptive=True  # Enable adaptive rate limiting
        )
        
        # Check if detailed logging is enabled
        if settings.telegram_api_detailed_logging:
            api_logger.info("Enhanced Telegram API logging is ENABLED")
        else:
            api_logger.info("Enhanced Telegram API logging is DISABLED")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            # Configure connection pooling
            connector = aiohttp.TCPConnector(
                limit=settings.http_max_connections,
                limit_per_host=settings.http_max_connections_per_host,
                ttl_dns_cache=300,
                keepalive_timeout=30,
                force_close=False,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(total=settings.telegram_timeout_sec)
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            logger.info("Created aiohttp session with connection pooling")
        
        return self._session
    
    async def close(self):
        """Close aiohttp session and log statistics."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Closed aiohttp session")
            
            # Log final statistics
            self._log_statistics()
    
    def _log_statistics(self):
        """Log API usage statistics."""
        total_requests = self.stats['total_requests']
        if total_requests == 0:
            return
        
        success_rate = (self.stats['successful_requests'] / total_requests) * 100
        avg_download_time = (
            self.stats['total_download_time_ms'] / total_requests 
            if total_requests > 0 else 0
        )
        total_mb = self.stats['total_bytes_downloaded'] / (1024 * 1024)
        
        api_logger.info("=" * 80)
        api_logger.info("Enhanced Telegram API Statistics Summary:")
        api_logger.info(f"  Total Requests: {total_requests}")
        api_logger.info(f"  Successful: {self.stats['successful_requests']} ({success_rate:.1f}%)")
        api_logger.info(f"  Failed: {self.stats['failed_requests']}")
        api_logger.info(f"  Rate Limited: {self.stats['rate_limited_requests']}")
        api_logger.info(f"  Retry Attempts: {self.stats['retry_attempts']}")
        api_logger.info(f"  Total Downloaded: {total_mb:.2f} MB")
        api_logger.info(f"  Average Response Time: {avg_download_time:.1f}ms")
        
        if self.stats['errors_by_type']:
            api_logger.info("  Errors by Type:")
            for error_type, count in sorted(
                self.stats['errors_by_type'].items(), 
                key=lambda x: x[1], 
                reverse=True
            ):
                api_logger.info(f"    {error_type}: {count}")
        
        api_logger.info("=" * 80)
    
    def _record_success(self, elapsed_ms: int, bytes_downloaded: int = 0):
        """Record successful API request."""
        self.stats['total_requests'] += 1
        self.stats['successful_requests'] += 1
        self.stats['total_download_time_ms'] += elapsed_ms
        self.stats['total_bytes_downloaded'] += bytes_downloaded
    
    def _record_error(self, error_type: str, elapsed_ms: int):
        """Record failed API request."""
        self.stats['total_requests'] += 1
        self.stats['failed_requests'] += 1
        self.stats['total_download_time_ms'] += elapsed_ms
        
        if error_type not in self.stats['errors_by_type']:
            self.stats['errors_by_type'][error_type] = 0
        self.stats['errors_by_type'][error_type] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current API statistics."""
        stats = self.stats.copy()
        stats['rate_limit_detected'] = self.rate_limit_detected
        stats['rate_limit_reset_time'] = self.rate_limit_reset_time
        return stats
    
    def _is_rate_limited(self) -> bool:
        """Check if we're currently rate limited."""
        if not self.rate_limit_detected:
            return False
        return time.time() < self.rate_limit_reset_time
    
    def _handle_rate_limit(self, retry_after: Optional[int] = None):
        """Handle rate limiting from Telegram API."""
        self.rate_limit_detected = True
        self.stats['rate_limited_requests'] += 1
        
        # Calculate reset time
        if retry_after:
            self.rate_limit_reset_time = time.time() + retry_after
            api_logger.warning(f"Rate limited by Telegram API. Retry after {retry_after} seconds")
        else:
            # Default to exponential backoff
            self.rate_limit_reset_time = time.time() + self.base_retry_delay
            api_logger.warning("Rate limited by Telegram API. Using exponential backoff")
        
        logger.warning(f"Rate limit detected. Will retry after {self.rate_limit_reset_time - time.time():.1f} seconds")
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        delay = min(self.base_retry_delay * (2 ** attempt), self.max_retry_delay)
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry logic."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            # Check if we're rate limited
            if self._is_rate_limited():
                wait_time = self.rate_limit_reset_time - time.time()
                if wait_time > 0:
                    api_logger.info(f"Waiting for rate limit to reset: {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            
            try:
                result = await func(*args, **kwargs)
                
                # If successful, reset rate limit state
                if result is not None:
                    self.rate_limit_detected = False
                    self.rate_limit_reset_time = 0
                
                return result
                
            except Exception as e:
                last_exception = e
                self.stats['retry_attempts'] += 1
                
                # Do not retry on explicit TelegramAPIError (e.g., invalid file_id, 400/403/404, etc.)
                if isinstance(e, TelegramAPIError):
                    raise e

                # Check if this is a rate limit error
                if hasattr(e, 'status') and e.status == 429:
                    # Extract retry-after header if available
                    retry_after = None
                    if hasattr(e, 'headers') and 'retry-after' in e.headers:
                        try:
                            retry_after = int(e.headers['retry-after'])
                        except (ValueError, TypeError):
                            pass
                    
                    self._handle_rate_limit(retry_after)
                    
                    if attempt < self.max_retries:
                        delay = self._calculate_retry_delay(attempt)
                        api_logger.info(f"Rate limit hit. Retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries})")
                        await asyncio.sleep(delay)
                        continue
                
                # For non-rate-limit errors, use standard exponential backoff
                if attempt < self.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    api_logger.warning(f"Request failed. Retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                    await asyncio.sleep(delay)
                    continue
                
                # Max retries reached
                break
        
        # All retries failed
        if last_exception:
            raise last_exception
        return None
    
    async def get_file_info(self, file_id: str) -> Optional[dict]:
        """Get file information from Telegram Bot API with retry logic and queue."""
        async def _get_with_retry(file_id):
            return await self._retry_with_backoff(self._get_file_info_internal, file_id)
        
        return await self.request_queue.execute(_get_with_retry, file_id)
    
    async def _get_file_info_internal(self, file_id: str) -> Optional[dict]:
        """Internal method to get file information from Telegram Bot API."""
        url = f"{self.api_base_url}/bot{self.bot_token}/getFile"
        params = {"file_id": file_id}
        
        # Start timing
        start_time = time.time()
        request_id = f"getFile-{file_id[:8]}"
        
        if settings.telegram_api_detailed_logging:
            api_logger.info(f"[{request_id}] 🌐 Telegram API: getFile request for file_id={file_id}")
            api_logger.debug(f"[{request_id}] URL: {self.api_base_url}/bot****/getFile")
            api_logger.debug(f"[{request_id}] Params: file_id={file_id}")
        
        session = await self._get_session()
        async with session.get(url, params=params) as response:
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Log response headers
            if settings.telegram_api_detailed_logging:
                api_logger.debug(f"[{request_id}] Response Status: {response.status}")
                api_logger.debug(f"[{request_id}] Response Headers: {dict(response.headers)}")
                api_logger.debug(f"[{request_id}] Response Time: {elapsed_ms}ms")
            
            # Handle rate limiting
            if response.status == 429:
                retry_after = None
                if 'retry-after' in response.headers:
                    try:
                        retry_after = int(response.headers['retry-after'])
                    except (ValueError, TypeError):
                        pass
                
                self._handle_rate_limit(retry_after)
                
                # Create a custom exception with status and headers
                error = aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=429,
                    message="Too Many Requests"
                )
                error.headers = response.headers
                raise error
            
            if response.status == 200:
                data = await response.json()
                
                if data.get("ok"):
                    result = data.get("result", {})
                    file_size = result.get("file_size", "unknown")
                    file_path = result.get("file_path", "unknown")
                    
                    # Record success
                    self._record_success(elapsed_ms)
                    
                    if settings.telegram_api_detailed_logging:
                        api_logger.info(
                            f"[{request_id}] ✓ getFile SUCCESS - "
                            f"file_id={file_id}, path={file_path}, size={file_size} bytes, "
                            f"time={elapsed_ms}ms"
                        )
                    return result
                else:
                    error_code = int(data.get("error_code", 400) or 400)
                    error_desc = data.get("description", "Bad Request")
                    
                    # Record error
                    self._record_error(f"API_ERROR_{error_code}", elapsed_ms)
                    
                    api_logger.error(
                        f"[{request_id}] ✗ Telegram API Error - "
                        f"code={error_code}, description={error_desc}, "
                        f"file_id={file_id}, time={elapsed_ms}ms"
                    )
                    logger.error(f"Telegram API error for {file_id}: [{error_code}] {error_desc}")
                    
                    # If Telegram signals Too Many Requests via body, handle as rate limit
                    if error_code == 429:
                        self._handle_rate_limit()
                        err = aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=429,
                            message=error_desc
                        )
                        raise err
                    
                    # Non-retriable: propagate exact code and message
                    raise TelegramAPIError(error_code, error_desc)
            else:
                # Non-200 HTTP status
                response_text = await response.text()
                
                # Special case: invalid file_id should NOT be retried
                if response.status == 400:
                    # Try parse JSON to inspect description
                    desc_lower = ""
                    try:
                        data_json = await response.json(content_type=None)
                        desc_lower = str(data_json.get("description", "")).lower()
                    except Exception:
                        desc_lower = response_text.lower()
                    
                    if "invalid file_id" in desc_lower or "invalid file id" in desc_lower:
                        self._record_error("HTTP_400_INVALID_FILE_ID", elapsed_ms)
                        api_logger.error(
                            f"[{request_id}] ✗ INVALID FILE_ID (400) - file_id={file_id}, time={elapsed_ms}ms"
                        )
                        logger.warning(
                            f"HTTP 400 invalid file_id for {file_id}: {response_text[:200]}"
                        )
                        # Propagate exact status/message (no retry)
                        # Try to extract description from JSON if possible
                        try:
                            data_json2 = await response.json(content_type=None)
                            description_exact = str(data_json2.get("description", response_text))
                        except Exception:
                            description_exact = response_text
                        raise TelegramAPIError(400, description_exact[:200])
                
                # Record error for other HTTP statuses and propagate exact status/message
                self._record_error(f"HTTP_{response.status}", elapsed_ms)
                
                api_logger.error(
                    f"[{request_id}] ✗ HTTP Error {response.status} - "
                    f"file_id={file_id}, time={elapsed_ms}ms"
                )
                
                if settings.telegram_api_detailed_logging:
                    api_logger.debug(f"[{request_id}] Response Body: {response_text[:500]}")
                
                logger.error(
                    f"HTTP {response.status} error getting file info for {file_id}: {response_text[:200]}"
                )
                
                if response.status == 429:
                    # Keep 429 as retriable
                    error = aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Too Many Requests"
                    )
                    error.headers = response.headers
                    raise error
                
                # Non-retriable: propagate exact status and body snippet
                raise TelegramAPIError(response.status, response_text[:200])
    
    async def download_file(self, file_path: str) -> Optional[bytes]:
        """Download file content from Telegram with retry logic and queue."""
        async def _download_with_retry(file_path):
            return await self._retry_with_backoff(self._download_file_internal, file_path)
        
        return await self.request_queue.execute(_download_with_retry, file_path)
    
    async def _download_file_internal(self, file_path: str) -> Optional[bytes]:
        """Internal method to download file content from Telegram."""
        url = f"{self.download_base_url}{self.bot_token}/{file_path}"
        
        # Start timing
        start_time = time.time()
        request_id = f"download-{file_path.split('/')[-1][:12]}"
        
        if settings.telegram_api_detailed_logging:
            api_logger.info(f"[{request_id}] 🌐 Telegram API: downloadFile request for file_path={file_path}")
            api_logger.debug(f"[{request_id}] URL: {self.download_base_url}****/{file_path}")
            api_logger.debug(f"[{request_id}] File Path: {file_path}")
        
        session = await self._get_session()
        async with session.get(url) as response:
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Log response info
            if settings.telegram_api_detailed_logging:
                content_length = response.headers.get('Content-Length', 'unknown')
                content_type = response.headers.get('Content-Type', 'unknown')
                
                api_logger.debug(f"[{request_id}] Response Status: {response.status}")
                api_logger.debug(f"[{request_id}] Content-Type: {content_type}")
                api_logger.debug(f"[{request_id}] Content-Length: {content_length} bytes")
            
            # Handle rate limiting
            if response.status == 429:
                retry_after = None
                if 'retry-after' in response.headers:
                    try:
                        retry_after = int(response.headers['retry-after'])
                    except (ValueError, TypeError):
                        pass
                
                self._handle_rate_limit(retry_after)
                
                # Create a custom exception with status and headers
                error = aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=429,
                    message="Too Many Requests"
                )
                error.headers = response.headers
                raise error
            
            if response.status == 200:
                content = await response.read()
                download_time_ms = int((time.time() - start_time) * 1000)
                actual_size = len(content)
                
                # Check file size limit
                max_size = settings.max_file_size_mb * 1024 * 1024
                if actual_size > max_size:
                    # Record as error
                    self._record_error("FILE_TOO_LARGE", download_time_ms)
                    
                    api_logger.warning(
                        f"[{request_id}] ⚠ FILE TOO LARGE - "
                        f"size={actual_size} bytes, max={max_size} bytes, "
                        f"file_path={file_path}"
                    )
                    logger.warning(
                        f"File too large: {actual_size} bytes (max: {max_size}) - {file_path}"
                    )
                    return None
                
                # Record success
                self._record_success(download_time_ms, actual_size)
                
                # Calculate download speed
                speed_mbps = (actual_size / (1024 * 1024)) / (download_time_ms / 1000) if download_time_ms > 0 else 0
                
                if settings.telegram_api_detailed_logging:
                    api_logger.info(
                        f"[{request_id}] ✓ downloadFile SUCCESS - "
                        f"size={actual_size} bytes, time={download_time_ms}ms, "
                        f"speed={speed_mbps:.2f} MB/s, file_path={file_path}"
                    )
                
                return content
                
            elif response.status == 404:
                self._record_error("HTTP_404_NOT_FOUND", elapsed_ms)
                
                api_logger.error(
                    f"[{request_id}] ✗ FILE NOT FOUND (404) - "
                    f"file_path={file_path}, time={elapsed_ms}ms"
                )
                logger.error(f"File not found on Telegram servers: {file_path}")
                return None
                
            elif response.status == 403:
                self._record_error("HTTP_403_FORBIDDEN", elapsed_ms)
                
                api_logger.error(
                    f"[{request_id}] ✗ ACCESS DENIED (403) - "
                    f"file_path={file_path}, time={elapsed_ms}ms"
                )
                logger.error(f"Access denied to file (check bot token): {file_path}")
                return None
                
            else:
                response_text = await response.text()
                self._record_error(f"HTTP_{response.status}", elapsed_ms)
                
                api_logger.error(
                    f"[{request_id}] ✗ HTTP Error {response.status} - "
                    f"file_path={file_path}, time={elapsed_ms}ms"
                )
                
                if settings.telegram_api_detailed_logging:
                    api_logger.debug(f"[{request_id}] Response Body: {response_text[:500]}")
                
                logger.error(
                    f"HTTP {response.status} error downloading file {file_path}: {response_text[:200]}"
                )
                
                # Raise exception for retry logic
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=response_text[:200]
                )
    
    async def get_sticker_set(self, name: str) -> Optional[dict]:
        """Get sticker set from Telegram Bot API with retry logic and queue."""
        async def _get_with_retry(name):
            return await self._retry_with_backoff(self._get_sticker_set_internal, name)
        
        return await self.request_queue.execute(_get_with_retry, name)
    
    async def _get_sticker_set_internal(self, name: str) -> Optional[dict]:
        """Internal method to get sticker set from Telegram Bot API."""
        url = f"{self.api_base_url}/bot{self.bot_token}/getStickerSet"
        params = {"name": name}
        
        # Start timing
        start_time = time.time()
        request_id = f"getStickerSet-{name[:12]}"
        
        if settings.telegram_api_detailed_logging:
            api_logger.info(f"[{request_id}] 🌐 Telegram API: getStickerSet request for name={name}")
            api_logger.debug(f"[{request_id}] URL: {self.api_base_url}/bot****/getStickerSet")
            api_logger.debug(f"[{request_id}] Params: name={name}")
        
        session = await self._get_session()
        async with session.get(url, params=params) as response:
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Log response headers
            if settings.telegram_api_detailed_logging:
                api_logger.debug(f"[{request_id}] Response Status: {response.status}")
                api_logger.debug(f"[{request_id}] Response Headers: {dict(response.headers)}")
                api_logger.debug(f"[{request_id}] Response Time: {elapsed_ms}ms")
            
            # Handle rate limiting
            if response.status == 429:
                retry_after = None
                if 'retry-after' in response.headers:
                    try:
                        retry_after = int(response.headers['retry-after'])
                    except (ValueError, TypeError):
                        pass
                
                self._handle_rate_limit(retry_after)
                
                # Create a custom exception with status and headers
                error = aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=429,
                    message="Too Many Requests"
                )
                error.headers = response.headers
                raise error
            
            if response.status == 200:
                data = await response.json()
                
                if data.get("ok"):
                    result = data.get("result", {})
                    stickers_count = len(result.get("stickers", []))
                    
                    # Record success
                    self._record_success(elapsed_ms)
                    
                    if settings.telegram_api_detailed_logging:
                        api_logger.info(
                            f"[{request_id}] ✓ getStickerSet SUCCESS - "
                            f"name={name}, stickers_count={stickers_count}, "
                            f"time={elapsed_ms}ms"
                        )
                    return result
                else:
                    error_code = int(data.get("error_code", 400) or 400)
                    error_desc = data.get("description", "Bad Request")
                    
                    # Record error
                    self._record_error(f"API_ERROR_{error_code}", elapsed_ms)
                    
                    api_logger.error(
                        f"[{request_id}] ✗ Telegram API Error - "
                        f"code={error_code}, description={error_desc}, "
                        f"name={name}, time={elapsed_ms}ms"
                    )
                    logger.error(f"Telegram API error for sticker set {name}: [{error_code}] {error_desc}")
                    
                    # If Telegram signals Too Many Requests via body, handle as rate limit
                    if error_code == 429:
                        self._handle_rate_limit()
                        err = aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=429,
                            message=error_desc
                        )
                        raise err
                    
                    # Non-retriable: propagate exact code and message
                    raise TelegramAPIError(error_code, error_desc)
            else:
                # Non-200 HTTP status
                response_text = await response.text()
                
                # Record error for other HTTP statuses and propagate exact status/message
                self._record_error(f"HTTP_{response.status}", elapsed_ms)
                
                api_logger.error(
                    f"[{request_id}] ✗ HTTP Error {response.status} - "
                    f"name={name}, time={elapsed_ms}ms"
                )
                
                if settings.telegram_api_detailed_logging:
                    api_logger.debug(f"[{request_id}] Response Body: {response_text[:500]}")
                
                logger.error(
                    f"HTTP {response.status} error getting sticker set {name}: {response_text[:200]}"
                )
                
                if response.status == 429:
                    # Keep 429 as retriable
                    error = aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Too Many Requests"
                    )
                    error.headers = response.headers
                    raise error
                
                # Non-retriable: propagate exact status and body snippet
                raise TelegramAPIError(response.status, response_text[:200])
    
    def detect_file_format(self, file_path: str, content: bytes) -> str:
        """Detect file format based on file path and content."""
        # Check file extension first
        if file_path.endswith('.tgs'):
            return 'tgs'
        elif file_path.endswith('.webm'):
            return 'webm'
        elif file_path.endswith('.webp'):
            return 'webp'
        elif file_path.endswith('.png'):
            return 'png'
        elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
            return 'jpg'
        
        # Check magic bytes
        if content.startswith(b'\x1f\x8b'):  # gzip/tgs
            return 'tgs'
        elif content.startswith(b'RIFF') and b'WEBM' in content[:20]:
            return 'webm'
        elif content.startswith(b'RIFF') and b'WEBP' in content[:20]:
            return 'webp'
        elif content.startswith(b'\x89PNG'):
            return 'png'
        elif content.startswith(b'\xff\xd8\xff'):
            return 'jpg'
        
        return 'unknown'
    
    def get_mime_type(self, file_format: str) -> str:
        """Get MIME type for file format."""
        mime_types = {
            'tgs': 'application/gzip',
            'webm': 'video/webm',
            'webp': 'image/webp',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'lottie': 'application/json'
        }
        return mime_types.get(file_format, 'application/octet-stream')
