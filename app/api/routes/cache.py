"""Cache management routes."""
from fastapi import APIRouter

from app.services.cache_manager import CacheManager
from app.handlers.cache_handler import CacheHandler


def create_cache_router(cache_manager: CacheManager) -> APIRouter:
    """Create cache router with cache manager dependency."""
    router = APIRouter()
    handler = CacheHandler(cache_manager)
    
    @router.get(
        "/cache/stats",
        summary="Cache Statistics",
        description="""
        Get comprehensive cache statistics including:
        
        - **Overall Statistics**: Total requests, cache hit rates, performance metrics
        - **Redis Cache**: Memory cache statistics and availability
        - **Disk Cache**: Persistent storage statistics and usage
        - **Telegram API**: API usage, rate limiting events, retry attempts
        - **Service Info**: Feature availability and configuration status
        """,
        tags=["Cache Management"],
        responses={
            200: {
                "description": "Comprehensive cache statistics",
                "content": {
                    "application/json": {
                        "example": {
                            "total_files": 1250,
                            "total_size_bytes": 245600000,
                            "cache_hit_rate": 87.5,
                            "redis": {"total_files": 45, "cache_hits": 1200},
                            "disk": {"total_files": 1250, "cache_hits": 800},
                            "telegram_api": {"total_requests": 450, "rate_limited_requests": 12}
                        }
                    }
                }
            }
        }
    )
    async def get_cache_stats():
        """Get comprehensive cache statistics."""
        return await handler.get_cache_stats()
    
    @router.delete(
        "/cache/{file_id}",
        summary="Delete File from Cache",
        description="Delete a specific file from both Redis and disk cache",
        tags=["Cache Management"],
        responses={
            200: {"description": "File deleted successfully"},
            404: {"description": "File not found in cache"}
        }
    )
    async def delete_from_cache(file_id: str):
        """Delete specific file from cache."""
        return await handler.delete_from_cache(file_id)
    
    @router.delete(
        "/cache/all",
        summary="Clear All Cache",
        description="Clear all cached files from both Redis and disk cache",
        tags=["Cache Management"],
        responses={
            200: {"description": "All cache cleared successfully"}
        }
    )
    async def clear_all_cache():
        """Clear all cached files."""
        return await handler.clear_all_cache()
    
    @router.post(
        "/cache/cleanup",
        summary="Cleanup Cache",
        description="""
        Clean up expired and old files from cache:
        
        - Remove expired files (past TTL)
        - Remove oldest files if cache exceeds size limit
        - Optimize cache performance and storage usage
        """,
        tags=["Cache Management"],
        responses={
            200: {"description": "Cache cleanup completed successfully"}
        }
    )
    async def cleanup_cache():
        """Clean up expired and old files from cache."""
        return await handler.cleanup_cache()
    
    @router.get(
        "/cache/strategy",
        summary="Cache Strategy Information",
        description="Get information about current cache strategy configuration"
    )
    async def get_cache_strategy():
        """Get cache strategy configuration."""
        return handler.get_cache_strategy()
    
    return router

