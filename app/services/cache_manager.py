import asyncio
import logging
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from app.services.redis import RedisService
from app.services.disk_cache import DiskCacheService
from app.services.telegram_enhanced import TelegramServiceEnhanced, TelegramAPIError
from app.services.converter import ConverterService
from app.services.cache_strategy import CacheStrategy
from app.services.cache.cache_chain import CacheChain
from app.models.responses import StickerCache
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Multi-level cache manager combining Redis and disk cache."""
    
    def __init__(self):
        self.redis_service = RedisService()
        self.disk_cache_service = DiskCacheService()
        self.telegram_service = TelegramServiceEnhanced()
        self.converter_service = ConverterService()
        self.cache_strategy = CacheStrategy()
        
        # Initialize cache chain
        self.cache_chain = CacheChain(
            self.redis_service,
            self.disk_cache_service,
            self.cache_strategy,
            self.converter_service
        )
        
        # Statistics
        self.stats = {
            'redis_hits': 0,
            'redis_misses': 0,
            'disk_hits': 0,
            'disk_misses': 0,
            'telegram_api_calls': 0,
            'conversions_performed': 0,
            'total_requests': 0,
        }
        
        logger.info("CacheManager initialized with multi-level caching")
    
    async def connect(self):
        """Connect to Redis service."""
        if not settings.redis_enabled:
            logger.info("Redis cache is disabled via REDIS_ENABLED=false")
            self.redis_service.redis = None
            return
        
        try:
            await self.redis_service.connect()
            logger.info("CacheManager connected to Redis")
        except Exception as e:
            logger.warning(f"CacheManager: Redis not available: {e}")
            self.redis_service.redis = None
    
    async def disconnect(self):
        """Disconnect from services."""
        await self.redis_service.disconnect()
        await self.telegram_service.close()
        logger.info("CacheManager disconnected")
    
    async def get_sticker(self, file_id: str) -> Optional[Tuple[bytes, str, bool]]:
        """
        Get sticker with multi-level caching strategy.
        
        Returns:
            Tuple of (content, mime_type, was_converted) or None
        """
        request_start = time.time()
        self.stats['total_requests'] += 1
        
        # Level 1: Check Redis cache (fastest)
        result = await self._check_redis(file_id, request_start)
        if result:
            return result
        
        # Level 2: Check disk cache (medium speed)
        result = await self._check_disk(file_id, request_start)
        if result:
            return result
        
        # Level 3: Fetch from Telegram API (slowest)
        cache_check_time = int((time.time() - request_start) * 1000)
        logger.info(
            f"📥 CACHE: MISS - no cache hit, will fetch from Telegram API, "
            f"file_id={file_id}, cache_check_time={cache_check_time}ms"
        )
        telegram_start = time.time()
        result = await self._fetch_from_telegram(file_id)
        telegram_time = int((time.time() - telegram_start) * 1000)
        total_time = int((time.time() - request_start) * 1000)
        
        if telegram_time > 10000:  # Log very slow Telegram API calls (>10s)
            logger.warning(
                f"Slow Telegram API fetch for {file_id}: telegram_time={telegram_time}ms, "
                f"total_time={total_time}ms"
            )
        else:
            logger.info(
                f"Telegram API fetch completed for {file_id}: telegram_time={telegram_time}ms, "
                f"total_time={total_time}ms"
            )
        
        return result
    
    async def get_sticker_set(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get sticker set with Redis caching.
        
        Args:
            name: Sticker set name
            
        Returns:
            Sticker set JSON data or None
        """
        # Check Redis cache first
        cached_set = await self.redis_service.get_sticker_set(name)
        if cached_set:
            logger.info(f"Retrieved sticker set {name} from Redis cache")
            return cached_set
        
        # Fetch from Telegram API
        logger.info(f"Fetching sticker set {name} from Telegram API")
        try:
            sticker_set = await self.telegram_service.get_sticker_set(name)
            if sticker_set:
                # Cache in Redis
                await self.redis_service.set_sticker_set(name, sticker_set)
                logger.info(f"Cached sticker set {name} in Redis")
                return sticker_set
            return None
        except TelegramAPIError as te:
            logger.error(f"Telegram API error getting sticker set {name}: [{te.status}] {te.description}")
            raise te
        except RuntimeError as e:
            # Handle "Event loop is closed" errors - re-raise to avoid silent failures
            if "Event loop is closed" in str(e):
                logger.error(f"Event loop closed while getting sticker set {name}: {e}")
                raise
            logger.error(f"Runtime error getting sticker set {name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting sticker set {name}: {e}")
            return None
    
    async def _check_redis(
        self, 
        file_id: str, 
        request_start: float
    ) -> Optional[Tuple[bytes, str, bool]]:
        """Check Redis cache (Level 1)."""
        # Store current stats before check
        prev_redis_hits = self.cache_chain.stats['redis_hits']
        prev_redis_misses = self.cache_chain.stats['redis_misses']
        
        result = await self.cache_chain.check_redis(file_id, request_start)
        
        # Sync stats from cache chain to main stats (additive)
        redis_hits_diff = self.cache_chain.stats['redis_hits'] - prev_redis_hits
        redis_misses_diff = self.cache_chain.stats['redis_misses'] - prev_redis_misses
        
        self.stats['redis_hits'] += redis_hits_diff
        self.stats['redis_misses'] += redis_misses_diff
        
        return result
    
    async def _check_disk(
        self, 
        file_id: str, 
        request_start: float
    ) -> Optional[Tuple[bytes, str, bool]]:
        """Check disk cache (Level 2)."""
        # Store current stats before check
        prev_disk_hits = self.cache_chain.stats['disk_hits']
        prev_disk_misses = self.cache_chain.stats['disk_misses']
        
        result = await self.cache_chain.check_disk(file_id, request_start, self.redis_service)
        
        # Sync stats from cache chain to main stats (additive)
        disk_hits_diff = self.cache_chain.stats['disk_hits'] - prev_disk_hits
        disk_misses_diff = self.cache_chain.stats['disk_misses'] - prev_disk_misses
        
        self.stats['disk_hits'] += disk_hits_diff
        self.stats['disk_misses'] += disk_misses_diff
        
        return result
    
    async def _fetch_from_telegram(self, file_id: str) -> Optional[Tuple[bytes, str, bool]]:
        """Fetch sticker from Telegram API and cache it."""
        try:
            self.stats['telegram_api_calls'] += 1
            
            # Get file info from Telegram
            try:
                file_info = await self.telegram_service.get_file_info(file_id)
            except TelegramAPIError as te:
                # Log client errors (4xx) as warnings, server errors (5xx) as errors
                if 400 <= te.status < 500:
                    logger.warning(f"Telegram API client error for {file_id}: [{te.status}] {te.description}")
                else:
                    logger.error(f"Telegram API error for {file_id}: [{te.status}] {te.description}")
                # Propagate for FastAPI layer to convert into HTTP response with same status/message
                raise te
            if not file_info:
                logger.error(f"Could not get file info for {file_id}")
                return None
            
            file_path = file_info.get('file_path')
            if not file_path:
                logger.error(f"No file path in response for {file_id}")
                return None
            
            # Download file content
            content = await self.telegram_service.download_file(file_path)
            if not content:
                logger.error(f"Could not download file for {file_id}")
                return None
            
            # Detect file format
            file_format = self.telegram_service.detect_file_format(file_path, content)
            mime_type = self.telegram_service.get_mime_type(file_format)
            
            # Do NOT store original TGS files on disk (only converted lottie to save space)
            # Non-TGS files (webp, png, etc.) can be stored as they won't be converted
            if settings.disk_cache_enabled and file_format != 'tgs':
                try:
                    await self.disk_cache_service.store_file(
                        file_id, content, file_format, 
                        original_size=len(content), converted=False
                    )
                    logger.debug(f"Stored {file_format} file {file_id} on disk (non-TGS)")
                except Exception as e:
                    logger.error(f"Error storing in disk cache: {e}")
            
            # Store in Redis using intelligent strategy
            if self.redis_service.redis and self.cache_strategy.should_cache_in_redis(
                file_format, len(content), False
            ):
                try:
                    cache_entry = StickerCache(
                        file_id=file_id,
                        file_data=content,
                        mime_type=mime_type,
                        file_name=f"{file_id}.{file_format}",
                        file_size=len(content),
                        original_format=file_format,
                        output_format=file_format,
                        telegram_file_path=file_path,
                        last_updated=datetime.now(),
                        conversion_time_ms=None,
                        is_converted=False
                    )
                    await self.redis_service.set_sticker(cache_entry)
                    logger.debug(f"Stored {file_format} file {file_id} in Redis")
                except Exception as e:
                    logger.error(f"Error storing {file_format} file in Redis: {e}")
            
            # Handle TGS files - convert and cache
            if file_format == 'tgs':
                converted_content = await self._convert_and_cache(file_id, content)
                if converted_content:
                    return converted_content, 'application/json', True
            
            # Return non-TGS files as-is
            return content, mime_type, False
            
        except Exception as e:
            logger.error(f"Error fetching from Telegram for {file_id}: {e}")
            return None
    
    async def _convert_and_cache(self, file_id: str, content: bytes) -> Optional[bytes]:
        """Convert TGS to Lottie and cache the result."""
        try:
            self.stats['conversions_performed'] += 1
            
            # Convert TGS to Lottie
            conversion_result = await self.converter_service.convert_tgs_to_lottie(content)
            if not conversion_result:
                logger.error(f"Conversion failed for {file_id}")
                return None
            
            # Extract content from tuple (format, content)
            converted_format, converted_content = conversion_result
            
            # Store converted version in disk cache
            if settings.disk_cache_enabled:
                try:
                    await self.disk_cache_service.store_file(
                        file_id, converted_content, converted_format,
                        original_size=len(content), converted=True
                    )
                except Exception as e:
                    logger.error(f"Error storing converted file in disk cache: {e}")
            
            # Store converted version in Redis using strategy
            if self.redis_service.redis and self.cache_strategy.should_cache_in_redis(
                converted_format, len(converted_content), True
            ):
                try:
                    cache_entry = StickerCache(
                        file_id=file_id,
                        file_data=converted_content,
                        mime_type='application/json',
                        file_name=f"{file_id}.{converted_format}",
                        file_size=len(converted_content),
                        original_format='tgs',
                        output_format=converted_format,
                        last_updated=datetime.now(),
                        is_converted=True
                    )
                    await self.redis_service.set_sticker(cache_entry)
                    logger.debug(f"Stored converted {converted_format} file {file_id} in Redis")
                except Exception as e:
                    logger.error(f"Error storing converted {converted_format} file in Redis: {e}")
            
            return converted_content
            
        except Exception as e:
            logger.error(f"Error converting and caching {file_id}: {e}")
            return None
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        import asyncio
        
        stats = self.stats.copy()
        
        # Add Redis stats with timeout
        if self.redis_service.redis:
            try:
                redis_stats = await asyncio.wait_for(
                    self.redis_service.get_cache_stats(),
                    timeout=5.0  # 5 seconds timeout
                )
                if redis_stats:
                    # Convert CacheStats to dict and add formatted fields
                    stats['redis'] = {
                        'total_files': redis_stats.total_files,
                        'total_size_bytes': redis_stats.total_size_bytes,
                        'total_size_mb': round(redis_stats.total_size_bytes / (1024 * 1024), 2),
                        'converted_files': redis_stats.converted_files,
                        'original_files': redis_stats.original_files,
                        'last_updated': redis_stats.last_updated.isoformat() if redis_stats.last_updated else None,
                        'file_types': redis_stats.file_types,
                        'available': True
                    }
                else:
                    stats['redis'] = {'available': False}
            except asyncio.TimeoutError:
                logger.warning("Redis stats timeout - Redis may have too many keys")
                stats['redis'] = {'timeout': True, 'available': True}
            except Exception as e:
                logger.error(f"Error getting Redis stats: {e}")
                stats['redis'] = {'error': str(e)}
        else:
            stats['redis'] = {'available': False}
        
        # Add disk cache stats with timeout
        if settings.disk_cache_enabled:
            try:
                disk_stats = await asyncio.wait_for(
                    self.disk_cache_service.get_cache_stats(),
                    timeout=5.0  # 5 seconds timeout
                )
                stats['disk'] = disk_stats
            except asyncio.TimeoutError:
                logger.warning("Disk cache stats timeout")
                stats['disk'] = {'timeout': True, 'enabled': True}
            except Exception as e:
                logger.error(f"Error getting disk cache stats: {e}")
                stats['disk'] = {'error': str(e)}
        else:
            stats['disk'] = {'enabled': False}
        
        # Add Telegram API stats
        try:
            telegram_stats = self.telegram_service.get_statistics()
            
            # Add formatted statistics with rounding
            if isinstance(telegram_stats, dict):
                telegram_stats_formatted = telegram_stats.copy()
                
                # Calculate and round success rate
                total = telegram_stats.get('total_requests', 0)
                successful = telegram_stats.get('successful_requests', 0)
                if total > 0:
                    telegram_stats_formatted['success_rate_percent'] = round((successful / total) * 100, 1)
                else:
                    telegram_stats_formatted['success_rate_percent'] = 0
                
                # Calculate and round average download time
                if total > 0:
                    telegram_stats_formatted['avg_download_time_ms'] = round(
                        telegram_stats.get('total_download_time_ms', 0) / total, 1
                    )
                else:
                    telegram_stats_formatted['avg_download_time_ms'] = 0
                
                # Convert bytes to MB and round
                bytes_downloaded = telegram_stats.get('total_bytes_downloaded', 0)
                telegram_stats_formatted['total_bytes_mb'] = round(bytes_downloaded / (1024 * 1024), 2)
                
                stats['telegram_api'] = telegram_stats_formatted
            else:
                stats['telegram_api'] = telegram_stats
                
        except Exception as e:
            logger.error(f"Error getting Telegram API stats: {e}")
            stats['telegram_api'] = {'error': str(e)}
        
        # Calculate overall cache hit rates
        total_cache_requests = stats['redis_hits'] + stats['redis_misses'] + stats['disk_hits'] + stats['disk_misses']
        if total_cache_requests > 0:
            stats['overall_cache_hit_rate'] = round(((stats['redis_hits'] + stats['disk_hits']) / total_cache_requests) * 100, 1)
        else:
            stats['overall_cache_hit_rate'] = 0
        
        return stats
    
    async def cleanup_cache(self) -> Dict[str, int]:
        """Clean up both Redis and disk cache."""
        cleanup_results = {}
        
        # Clean up Redis cache
        if self.redis_service.redis:
            try:
                redis_cleaned = await self.redis_service.cleanup_expired_stickers()
                cleanup_results['redis_cleaned'] = redis_cleaned
            except Exception as e:
                logger.error(f"Error cleaning Redis cache: {e}")
                cleanup_results['redis_error'] = str(e)
        
        # Clean up disk cache
        if settings.disk_cache_enabled:
            try:
                disk_cleaned = await self.disk_cache_service.cleanup_expired_files()
                cleanup_results['disk_cleaned'] = disk_cleaned
                
                # Also clean up old files if cache is too large
                current_stats = await self.disk_cache_service.get_cache_stats()
                if current_stats['total_size_mb'] > settings.disk_cache_max_size_mb:
                    target_size = int(settings.disk_cache_max_size_mb * 0.8)  # Clean to 80% of max
                    old_files_removed = await self.disk_cache_service.cleanup_oldest_files(target_size)
                    cleanup_results['old_files_removed'] = old_files_removed
                    
            except Exception as e:
                logger.error(f"Error cleaning disk cache: {e}")
                cleanup_results['disk_error'] = str(e)
        
        return cleanup_results
    
    async def clear_all_cache(self) -> Dict[str, int]:
        """Clear all cache data."""
        clear_results = {}
        
        # Clear Redis cache
        if self.redis_service.redis:
            try:
                redis_cleared = await self.redis_service.clear_cache()
                clear_results['redis_cleared'] = redis_cleared
            except Exception as e:
                logger.error(f"Error clearing Redis cache: {e}")
                clear_results['redis_error'] = str(e)
        
        # Clear disk cache
        if settings.disk_cache_enabled:
            try:
                disk_cleared = await self.disk_cache_service.clear_cache()
                clear_results['disk_cleared'] = disk_cleared
            except Exception as e:
                logger.error(f"Error clearing disk cache: {e}")
                clear_results['disk_error'] = str(e)
        
        return clear_results
