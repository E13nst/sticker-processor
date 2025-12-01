import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import redis.asyncio as redis
from app.config import settings
from app.models.responses import StickerCache, CacheStats

logger = logging.getLogger(__name__)


class RedisService:
    """Service for Redis operations."""
    
    def __init__(self):
        self.redis = None
        self.connection_pool = None
        self.ttl_days = settings.cache_ttl_days
    
    async def connect(self):
        """Connect to Redis with connection pooling."""
        try:
            # SSL support for Redis
            if hasattr(settings, 'redis_ssl_enabled') and settings.redis_ssl_enabled:
                import ssl
                
                # Create SSL context that accepts self-signed certificates
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Build Redis URL with SSL
                if settings.redis_password:
                    redis_url = f"rediss://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_database}"
                else:
                    redis_url = f"rediss://{settings.redis_host}:{settings.redis_port}/{settings.redis_database}"
                
                # Create Redis client with SSL
                self.redis = redis.from_url(
                    redis_url,
                    decode_responses=False,
                    max_connections=settings.redis_max_connections,
                    socket_keepalive=settings.redis_socket_keepalive,
                    socket_connect_timeout=settings.redis_socket_connect_timeout,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    ssl_cert_reqs='none',
                    ssl_check_hostname=False
                )
                logger.info("Connecting to Redis with SSL and connection pooling")
            else:
                # Build Redis URL without SSL
                if settings.redis_password:
                    redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_database}"
                else:
                    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_database}"
                
                # Create Redis client without SSL
                self.redis = redis.from_url(
                    redis_url,
                    decode_responses=False,
                    max_connections=settings.redis_max_connections,
                    socket_keepalive=settings.redis_socket_keepalive,
                    socket_connect_timeout=settings.redis_socket_connect_timeout,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                logger.info("Connecting to Redis with connection pooling")
            
            # Test connection
            await self.redis.ping()
            logger.info(f"Connected to Redis successfully with pool size: {settings.redis_max_connections}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Redis and close connection pool."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")
    
    def _get_cache_key(self, file_id: str) -> str:
        """Generate cache key for file."""
        return f"sticker:file:{file_id}"
    
    async def get_sticker(self, file_id: str) -> Optional[StickerCache]:
        """Get sticker from cache."""
        if not self.redis:
            return None
        
        try:
            key = self._get_cache_key(file_id)
            cached_data = await self.redis.get(key)
            
            if cached_data:
                # Deserialize cached data
                # Handle both bytes and str (for fakeredis compatibility)
                try:
                    if isinstance(cached_data, bytes):
                        data = json.loads(cached_data.decode('utf-8'))
                    else:
                        data = json.loads(cached_data)
                except (AttributeError, TypeError):
                    # For fakeredis, might need to convert differently
                    data = json.loads(str(cached_data, 'utf-8') if isinstance(cached_data, (bytes, bytearray)) else cached_data)
                
                # Convert base64 file_data back to bytes
                import base64
                file_data = base64.b64decode(data['file_data'])
                
                # Reconstruct StickerCache object
                sticker_cache = StickerCache(
                    file_id=data['file_id'],
                    file_data=file_data,
                    mime_type=data['mime_type'],
                    file_name=data['file_name'],
                    file_size=data['file_size'],
                    original_format=data['original_format'],
                    output_format=data['output_format'],
                    telegram_file_path=data.get('telegram_file_path'),
                    last_updated=datetime.fromisoformat(data['last_updated']),
                    conversion_time_ms=data.get('conversion_time_ms'),
                    is_converted=data['is_converted']
                )
                
                logger.info(f"Retrieved sticker {file_id} from cache")
                return sticker_cache
            else:
                logger.debug(f"Sticker {file_id} not found in cache")
                return None
                
        except Exception as e:
            logger.error(f"Error getting sticker {file_id} from cache: {e}")
            return None
    
    async def set_sticker(self, sticker_cache: StickerCache) -> bool:
        """Store sticker in cache."""
        if not self.redis:
            return False
        
        try:
            key = self._get_cache_key(sticker_cache.file_id)
            
            # Serialize data for storage
            import base64
            data = {
                'file_id': sticker_cache.file_id,
                'file_data': base64.b64encode(sticker_cache.file_data).decode('utf-8'),
                'mime_type': sticker_cache.mime_type,
                'file_name': sticker_cache.file_name,
                'file_size': sticker_cache.file_size,
                'original_format': sticker_cache.original_format,
                'output_format': sticker_cache.output_format,
                'telegram_file_path': sticker_cache.telegram_file_path,
                'last_updated': sticker_cache.last_updated.isoformat(),
                'conversion_time_ms': sticker_cache.conversion_time_ms,
                'is_converted': sticker_cache.is_converted
            }
            
            # Store with TTL
            ttl_seconds = self.ttl_days * 24 * 60 * 60
            json_data = json.dumps(data)
            # Ensure we pass bytes to setex for compatibility
            if isinstance(json_data, str):
                json_data = json_data.encode('utf-8')
            await self.redis.setex(key, ttl_seconds, json_data)
            
            logger.info(f"Stored sticker {sticker_cache.file_id} in cache")
            return True
            
        except Exception as e:
            logger.error(f"Error storing sticker {sticker_cache.file_id} in cache: {e}")
            return False
    
    async def delete_sticker(self, file_id: str) -> bool:
        """Delete sticker from cache."""
        if not self.redis:
            return False
        
        try:
            key = self._get_cache_key(file_id)
            result = await self.redis.delete(key)
            logger.info(f"Deleted sticker {file_id} from cache")
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting sticker {file_id} from cache: {e}")
            return False
    
    async def get_cache_stats(self) -> Optional[CacheStats]:
        """Get cache statistics."""
        if not self.redis:
            return None
        
        try:
            # Get all sticker keys
            pattern = "sticker:file:*"
            keys = await self.redis.keys(pattern)
            
            total_files = len(keys)
            total_size_bytes = 0
            converted_files = 0
            file_types = {}
            
            for key in keys:
                try:
                    cached_data = await self.redis.get(key)
                    if cached_data:
                        # Handle both bytes and str (for fakeredis compatibility)
                        try:
                            if isinstance(cached_data, bytes):
                                data = json.loads(cached_data.decode('utf-8'))
                            else:
                                data = json.loads(cached_data)
                        except (AttributeError, TypeError):
                            data = json.loads(str(cached_data, 'utf-8') if isinstance(cached_data, (bytes, bytearray)) else cached_data)
                        total_size_bytes += data.get('file_size', 0)
                        if data.get('is_converted', False):
                            converted_files += 1
                        
                        # Count file types
                        output_format = data.get('output_format', 'unknown')
                        file_types[output_format] = file_types.get(output_format, 0) + 1
                except Exception:
                    continue
            
            return CacheStats(
                total_files=total_files,
                total_size_bytes=total_size_bytes,
                converted_files=converted_files,
                original_files=total_files - converted_files,
                last_updated=datetime.now(),
                file_types=file_types
            )
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return None
    
    async def clear_all_cache(self) -> bool:
        """Clear all cached stickers."""
        if not self.redis:
            return False
        
        try:
            pattern = "sticker:file:*"
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} stickers from cache")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
