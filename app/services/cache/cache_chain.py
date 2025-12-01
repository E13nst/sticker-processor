"""Cache chain logic for multi-level caching."""
import logging
import time
from typing import Optional, Tuple

from app.config import settings
from app.models.responses import StickerCache
from datetime import datetime

logger = logging.getLogger(__name__)


class CacheChain:
    """Manages the cache chain: Redis -> Disk -> Telegram."""
    
    def __init__(self, redis_service, disk_cache_service, cache_strategy, converter_service):
        """Initialize cache chain with services."""
        self.redis_service = redis_service
        self.disk_cache_service = disk_cache_service
        self.cache_strategy = cache_strategy
        self.converter_service = converter_service
        self.stats = {
            'redis_hits': 0,
            'redis_misses': 0,
            'disk_hits': 0,
            'disk_misses': 0,
        }
    
    async def check_redis(
        self, 
        file_id: str, 
        request_start: float
    ) -> Optional[Tuple[bytes, str, bool]]:
        """
        Check Redis cache (Level 1).
        
        Args:
            file_id: Telegram file ID
            request_start: Request start time for logging
            
        Returns:
            Tuple of (content, mime_type, was_converted) if found, None otherwise
        """
        if not self.redis_service.redis:
            return None
        
        try:
            redis_start = time.time()
            cached_data = await self.redis_service.get_sticker(file_id)
            redis_time = int((time.time() - redis_start) * 1000)
            
            if cached_data:
                # Check if this file should be in Redis according to strategy
                if self.cache_strategy.should_cache_in_redis(
                    cached_data.output_format, 
                    cached_data.file_size, 
                    cached_data.is_converted
                ):
                    self.stats['redis_hits'] += 1
                    total_time = int((time.time() - request_start) * 1000)
                    logger.info(
                        f"📦 CACHE: Redis HIT - file_id={file_id}, format={cached_data.output_format}, "
                        f"size={cached_data.file_size} bytes, converted={cached_data.is_converted}, "
                        f"redis_time={redis_time}ms, total_time={total_time}ms"
                    )
                    return cached_data.file_data, cached_data.mime_type, cached_data.is_converted
                else:
                    logger.debug(f"Redis cache contains non-preferred format for {file_id}")
            
            self.stats['redis_misses'] += 1
            if redis_time > 100:  # Log slow Redis queries
                logger.warning(f"Slow Redis query for {file_id}: {redis_time}ms")
        except Exception as e:
            redis_time = int((time.time() - redis_start) * 1000) if 'redis_start' in locals() else 0
            logger.error(f"Redis cache error for {file_id} after {redis_time}ms: {e}")
            self.stats['redis_misses'] += 1
        
        return None
    
    async def check_disk(
        self, 
        file_id: str, 
        request_start: float,
        redis_service
    ) -> Optional[Tuple[bytes, str, bool]]:
        """
        Check disk cache (Level 2).
        
        Args:
            file_id: Telegram file ID
            request_start: Request start time for logging
            redis_service: Redis service for promoting to Redis
            
        Returns:
            Tuple of (content, mime_type, was_converted) if found, None otherwise
        """
        if not settings.disk_cache_enabled:
            return None
        
        try:
            disk_start = time.time()
            # Try different formats in disk cache
            # Note: 'tgs' excluded - we only cache converted lottie for TGS files
            formats_to_try = ['lottie', 'webp', 'png', 'jpg', 'webm']
            
            for format_name in formats_to_try:
                format_start = time.time()
                disk_content = await self.disk_cache_service.get_file(file_id, format_name)
                format_time = int((time.time() - format_start) * 1000)
                
                if disk_content:
                    disk_time = int((time.time() - disk_start) * 1000)
                    total_time = int((time.time() - request_start) * 1000)
                    self.stats['disk_hits'] += 1
                    logger.info(
                        f"📦 CACHE: Disk HIT - file_id={file_id}, format={format_name}, "
                        f"size={len(disk_content)} bytes, disk_time={disk_time}ms, "
                        f"total_time={total_time}ms"
                    )
                    
                    # Determine mime type and conversion status
                    if format_name == 'lottie':
                        mime_type = 'application/json'
                        is_converted = True
                    else:
                        mime_type = self.converter_service.get_output_mime_type(format_name)
                        is_converted = False
                    
                    # Store in Redis using intelligent strategy
                    if redis_service.redis and self.cache_strategy.should_cache_in_redis(
                        format_name, len(disk_content), is_converted
                    ):
                        try:
                            cache_entry = StickerCache(
                                file_id=file_id,
                                file_data=disk_content,
                                mime_type=mime_type,
                                file_name=f"{file_id}.{format_name}",
                                file_size=len(disk_content),
                                original_format='tgs' if is_converted else format_name,
                                output_format=format_name,
                                last_updated=datetime.now(),
                                is_converted=is_converted
                            )
                            await redis_service.set_sticker(cache_entry)
                            logger.debug(f"Stored {format_name} file {file_id} in Redis from disk cache")
                        except Exception as e:
                            logger.error(f"Error storing {format_name} file in Redis: {e}")
                    
                    return disk_content, mime_type, is_converted
            
            # No file found in disk cache
            disk_time = int((time.time() - disk_start) * 1000)
            self.stats['disk_misses'] += 1
            if disk_time > 500:  # Log slow disk cache checks
                logger.warning(f"Slow disk cache check for {file_id}: {disk_time}ms")
            
        except Exception as e:
            disk_time = int((time.time() - disk_start) * 1000) if 'disk_start' in locals() else 0
            logger.error(f"Disk cache error for {file_id} after {disk_time}ms: {e}")
            self.stats['disk_misses'] += 1
        
        return None

