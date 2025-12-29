"""Handler for cache-related business logic."""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException

from app.config import settings
from app.services.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class CacheHandler:
    """Handler for cache operations."""
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize cache handler with cache manager."""
        self.cache_manager = cache_manager
    
    # Redis cache methods
    async def get_redis_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if not self.cache_manager.redis_service.redis:
            return {"error": "Redis cache is not available"}
        
        stats = await self.cache_manager.redis_service.get_cache_stats()
        if stats:
            return {
                "total_files": stats.total_files,
                "total_size_bytes": stats.total_size_bytes,
                "total_size_mb": round(stats.total_size_bytes / (1024 * 1024), 2),
                "converted_files": stats.converted_files,
                "original_files": stats.original_files,
                "file_types": stats.file_types,
                "last_updated": stats.last_updated.isoformat() if stats.last_updated else None,
            }
        return {"error": "Failed to get Redis cache statistics"}
    
    async def clear_redis_cache(self) -> Dict[str, Any]:
        """Clear all Redis cache."""
        if not self.cache_manager.redis_service.redis:
            return {"error": "Redis cache is not available"}
        
        try:
            cleared = await self.cache_manager.redis_service.clear_cache()
            return {"message": f"Redis cache cleared", "files_removed": cleared}
        except Exception as e:
            logger.error(f"Error clearing Redis cache: {e}")
            return {"error": str(e)}
    
    async def cleanup_redis_cache(self) -> Dict[str, Any]:
        """Clean up expired Redis cache."""
        if not self.cache_manager.redis_service.redis:
            return {"error": "Redis cache is not available"}
        
        try:
            cleaned = await self.cache_manager.redis_service.cleanup_expired_stickers()
            return {"message": "Redis cache cleanup completed", "files_removed": cleaned}
        except Exception as e:
            logger.error(f"Error cleaning Redis cache: {e}")
            return {"error": str(e)}
    
    async def delete_from_redis(self, file_id: str) -> Dict[str, str]:
        """Delete specific file from Redis cache."""
        if not self.cache_manager.redis_service.redis:
            raise HTTPException(status_code=503, detail="Redis cache is not available")
        
        try:
            deleted = await self.cache_manager.redis_service.delete_sticker(file_id)
            if deleted:
                return {"message": f"File {file_id} deleted from Redis cache"}
            else:
                raise HTTPException(status_code=404, detail="File not found in Redis cache")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting from Redis: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Disk cache methods
    async def get_disk_stats(self) -> Dict[str, Any]:
        """Get disk cache statistics."""
        if not settings.disk_cache_enabled:
            return {"error": "Disk cache is not enabled"}
        
        try:
            stats = await self.cache_manager.disk_cache_service.get_cache_stats()
            return stats
        except Exception as e:
            logger.error(f"Error getting disk cache stats: {e}")
            return {"error": str(e)}

    async def get_disk_diagnostics(self, include_fs: bool = False, fs_scan_limit: int = 5000) -> Dict[str, Any]:
        """Get detailed disk cache diagnostics (DB path, process info, optional FS scan)."""
        if not settings.disk_cache_enabled:
            return {"error": "Disk cache is not enabled"}

        try:
            return await self.cache_manager.disk_cache_service.get_diagnostics(
                include_fs=include_fs,
                fs_scan_limit=fs_scan_limit
            )
        except Exception as e:
            logger.error(f"Error getting disk cache diagnostics: {e}")
            return {"error": str(e)}
    
    async def clear_disk_cache(self) -> Dict[str, Any]:
        """Clear all disk cache."""
        if not settings.disk_cache_enabled:
            return {"error": "Disk cache is not enabled"}
        
        try:
            cleared = await self.cache_manager.disk_cache_service.clear_cache()
            return {"message": "Disk cache cleared", "files_removed": cleared}
        except Exception as e:
            logger.error(f"Error clearing disk cache: {e}")
            return {"error": str(e)}
    
    async def cleanup_disk_cache(self) -> Dict[str, Any]:
        """Clean up expired and old files from disk cache."""
        if not settings.disk_cache_enabled:
            return {"error": "Disk cache is not enabled"}
        
        try:
            cleaned = await self.cache_manager.disk_cache_service.cleanup_expired_files()
            # Also clean up old files if cache is too large
            current_stats = await self.cache_manager.disk_cache_service.get_cache_stats()
            old_files_removed = 0
            if current_stats.get('total_size_mb', 0) > settings.disk_cache_max_size_mb:
                target_size = int(settings.disk_cache_max_size_mb * 0.8)  # Clean to 80% of max
                old_files_removed = await self.cache_manager.disk_cache_service.cleanup_oldest_files(target_size)
            
            return {
                "message": "Disk cache cleanup completed",
                "expired_files_removed": cleaned,
                "old_files_removed": old_files_removed
            }
        except Exception as e:
            logger.error(f"Error cleaning disk cache: {e}")
            return {"error": str(e)}
    
    async def delete_from_disk(self, file_id: str) -> Dict[str, str]:
        """Delete specific file from disk cache."""
        if not settings.disk_cache_enabled:
            raise HTTPException(status_code=503, detail="Disk cache is not enabled")
        
        try:
            # Try to delete both original and converted versions
            deleted_tgs = await self.cache_manager.disk_cache_service.delete_file(file_id, 'tgs')
            deleted_lottie = await self.cache_manager.disk_cache_service.delete_file(file_id, 'lottie')
            deleted_webp = await self.cache_manager.disk_cache_service.delete_file(file_id, 'webp')
            
            if deleted_tgs or deleted_lottie or deleted_webp:
                return {"message": f"File {file_id} deleted from disk cache"}
            else:
                raise HTTPException(status_code=404, detail="File not found in disk cache")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting from disk cache: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def get_cache_strategy(self) -> Dict[str, Any]:
        """Get cache strategy configuration."""
        return self.cache_manager.cache_strategy.get_strategy_stats()

