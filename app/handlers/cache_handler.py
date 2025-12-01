"""Handler for cache-related business logic."""
import logging
from typing import Dict, Any
from fastapi import HTTPException

from app.config import settings
from app.services.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class CacheHandler:
    """Handler for cache operations."""
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize cache handler with cache manager."""
        self.cache_manager = cache_manager
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return await self.cache_manager.get_cache_stats()
    
    async def delete_from_cache(self, file_id: str) -> Dict[str, str]:
        """
        Delete specific file from cache.
        
        Args:
            file_id: Telegram file ID to delete
            
        Returns:
            Dict with success message
            
        Raises:
            HTTPException: If file not found in cache
        """
        redis_deleted = False
        disk_deleted = False
        
        if self.cache_manager.redis_service.redis:
            try:
                redis_deleted = await self.cache_manager.redis_service.delete_sticker(file_id)
            except Exception as e:
                logger.error(f"Error deleting from Redis: {e}")
        
        if settings.disk_cache_enabled:
            try:
                # Try to delete both original and converted versions
                disk_deleted = await self.cache_manager.disk_cache_service.delete_file(file_id, 'tgs')
                disk_deleted = disk_deleted or await self.cache_manager.disk_cache_service.delete_file(file_id, 'lottie')
            except Exception as e:
                logger.error(f"Error deleting from disk cache: {e}")
        
        if not redis_deleted and not disk_deleted:
            raise HTTPException(status_code=404, detail="File not found in cache")
        
        return {"message": f"File {file_id} deleted from cache"}
    
    async def clear_all_cache(self) -> Dict[str, Any]:
        """Clear all cached files."""
        results = await self.cache_manager.clear_all_cache()
        return {"message": "All cache cleared", "details": results}
    
    async def cleanup_cache(self) -> Dict[str, Any]:
        """Clean up expired and old files from cache."""
        results = await self.cache_manager.cleanup_cache()
        return {"message": "Cache cleanup completed", "details": results}
    
    def get_cache_strategy(self) -> Dict[str, Any]:
        """Get cache strategy configuration."""
        return self.cache_manager.cache_strategy.get_strategy_stats()

