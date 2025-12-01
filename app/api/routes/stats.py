"""Statistics and information routes."""
from fastapi import APIRouter

from app.config import settings
from app.services.cache_manager import CacheManager


def create_stats_router(cache_manager: CacheManager) -> APIRouter:
    """Create statistics router with cache manager dependency."""
    router = APIRouter()
    
    @router.get(
        "/formats",
        summary="Supported Formats",
        description="Get list of supported input and output file formats",
        tags=["Information"],
        responses={
            200: {"description": "List of supported formats"}
        }
    )
    async def get_supported_formats():
        """Get list of supported file formats."""
        return {
            "supported_formats": {
                "input": ["tgs", "webm", "webp", "png", "jpg"],
                "output": ["lottie", "webm", "webp", "png", "jpg"],
                "conversions": {
                    "tgs": "lottie",
                    "webm": "webm (no conversion)",
                    "webp": "webp (no conversion)",
                    "png": "png (no conversion)",
                    "jpg": "jpg (no conversion)"
                }
            }
        }
    
    @router.get(
        "/api/stats",
        summary="API Statistics",
        description="""
        Get comprehensive API and cache statistics:
        
        - **Cache Statistics**: Multi-level cache performance and usage
        - **Service Info**: Feature availability and configuration status
        - **Performance Metrics**: Response times, hit rates, error rates
        - **System Status**: Redis availability, disk cache status
        """,
        tags=["Monitoring"],
        responses={
            200: {"description": "Comprehensive API and cache statistics"}
        }
    )
    async def get_api_statistics():
        """Get comprehensive API and cache statistics."""
        cache_stats = await cache_manager.get_cache_stats()
        
        return {
            "cache_statistics": cache_stats,
            "service_info": {
                "multi_level_caching": True,
                "adaptive_retry": True,
                "rate_limit_handling": True,
                "disk_cache_enabled": settings.disk_cache_enabled,
                "redis_available": cache_manager.redis_service.redis is not None
            }
        }
    
    return router

