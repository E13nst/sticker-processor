"""Cache management routes."""
from fastapi import APIRouter, Query

from app.services.cache_manager import CacheManager
from app.handlers.cache_handler import CacheHandler


def create_cache_router(cache_manager: CacheManager) -> APIRouter:
    """Create cache router with cache manager dependency."""
    router = APIRouter()
    handler = CacheHandler(cache_manager)
    
    # Redis cache endpoints
    @router.get(
        "/cache/redis/stats",
        summary="Redis Cache Statistics",
        description="Get Redis cache statistics including total files, size, and file types",
        tags=["Cache Management - Redis"],
        responses={
            200: {"description": "Redis cache statistics"},
            503: {"description": "Redis cache is not available"}
        }
    )
    async def get_redis_stats():
        """Get Redis cache statistics."""
        return await handler.get_redis_stats()
    
    @router.delete(
        "/cache/redis/clear",
        summary="Clear Redis Cache",
        description="Clear all files from Redis cache",
        tags=["Cache Management - Redis"],
        responses={
            200: {"description": "Redis cache cleared successfully"},
            503: {"description": "Redis cache is not available"}
        }
    )
    async def clear_redis_cache():
        """Clear all Redis cache."""
        return await handler.clear_redis_cache()
    
    @router.post(
        "/cache/redis/cleanup",
        summary="Cleanup Redis Cache",
        description="Clean up expired files from Redis cache",
        tags=["Cache Management - Redis"],
        responses={
            200: {"description": "Redis cache cleanup completed"},
            503: {"description": "Redis cache is not available"}
        }
    )
    async def cleanup_redis_cache():
        """Clean up expired Redis cache."""
        return await handler.cleanup_redis_cache()
    
    @router.delete(
        "/cache/redis/{file_id}",
        summary="Delete File from Redis Cache",
        description="Delete a specific file from Redis cache",
        tags=["Cache Management - Redis"],
        responses={
            200: {"description": "File deleted successfully"},
            404: {"description": "File not found in Redis cache"},
            503: {"description": "Redis cache is not available"}
        }
    )
    async def delete_from_redis(file_id: str):
        """Delete specific file from Redis cache."""
        return await handler.delete_from_redis(file_id)
    
    # Disk cache endpoints
    @router.get(
        "/cache/disk/stats",
        summary="Disk Cache Statistics",
        description="Get disk cache statistics including total files, size, and file types",
        tags=["Cache Management - Disk"],
        responses={
            200: {"description": "Disk cache statistics"},
            503: {"description": "Disk cache is not enabled"}
        }
    )
    async def get_disk_stats():
        """Get disk cache statistics."""
        return await handler.get_disk_stats()

    @router.get(
        "/cache/disk/diagnostics",
        summary="Disk Cache Diagnostics",
        description="""
        Detailed disk cache diagnostics for debugging production issues:
        
        - Which process (pid/hostname) you're hitting
        - Which cache directory and which SQLite metadata DB is being used
        - How many rows exist in metadata DB (and by format)
        - Optional best-effort filesystem scan to estimate how many cache files exist on disk
        """,
        tags=["Cache Management - Disk"],
        responses={
            200: {"description": "Disk cache diagnostics"},
            503: {"description": "Disk cache is not enabled"}
        }
    )
    async def get_disk_diagnostics(
        include_fs: bool = Query(False, description="Include a capped filesystem scan"),
        fs_scan_limit: int = Query(5000, ge=0, le=200000, description="Max files to scan when include_fs=true"),
    ):
        """Get disk cache diagnostics."""
        return await handler.get_disk_diagnostics(include_fs=include_fs, fs_scan_limit=fs_scan_limit)
    
    @router.delete(
        "/cache/disk/clear",
        summary="Clear Disk Cache",
        description="Clear all files from disk cache",
        tags=["Cache Management - Disk"],
        responses={
            200: {"description": "Disk cache cleared successfully"},
            503: {"description": "Disk cache is not enabled"}
        }
    )
    async def clear_disk_cache():
        """Clear all disk cache."""
        return await handler.clear_disk_cache()
    
    @router.post(
        "/cache/disk/cleanup",
        summary="Cleanup Disk Cache",
        description="""
        Clean up expired and old files from disk cache:
        
        - Remove expired files (past TTL)
        - Remove oldest files if cache exceeds size limit
        - Optimize cache performance and storage usage
        """,
        tags=["Cache Management - Disk"],
        responses={
            200: {"description": "Disk cache cleanup completed"},
            503: {"description": "Disk cache is not enabled"}
        }
    )
    async def cleanup_disk_cache():
        """Clean up expired and old files from disk cache."""
        return await handler.cleanup_disk_cache()
    
    @router.delete(
        "/cache/disk/{file_id}",
        summary="Delete File from Disk Cache",
        description="Delete a specific file from disk cache",
        tags=["Cache Management - Disk"],
        responses={
            200: {"description": "File deleted successfully"},
            404: {"description": "File not found in disk cache"},
            503: {"description": "Disk cache is not enabled"}
        }
    )
    async def delete_from_disk(file_id: str):
        """Delete specific file from disk cache."""
        return await handler.delete_from_disk(file_id)
    
    @router.get(
        "/cache/strategy",
        summary="Cache Strategy Information",
        description="Get information about current cache strategy configuration",
        tags=["Cache Management"]
    )
    async def get_cache_strategy():
        """Get cache strategy configuration."""
        return handler.get_cache_strategy()
    
    return router

