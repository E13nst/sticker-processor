"""Sticker routes."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.cache_manager import CacheManager
from app.handlers.sticker_handler import StickerHandler


def create_sticker_router(cache_manager: CacheManager) -> APIRouter:
    """Create sticker router with cache manager dependency."""
    router = APIRouter()
    handler = StickerHandler(cache_manager)
    
    @router.get(
        "/stickers/{file_id}",
        response_class=StreamingResponse,
        summary="Get Sticker",
        description="""
        Get a sticker by file ID with intelligent multi-level caching:
        
        1. **Redis Cache** (fastest) - Check in-memory cache first
        2. **Disk Cache** (medium) - Check persistent disk storage
        3. **Telegram API** (fallback) - Fetch from Telegram with adaptive retry
        
        **Features:**
        - Automatic TGS to Lottie conversion
        - Rate limiting protection with smart retry
        - Multi-format support (TGS, WebM, WebP, PNG, JPG)
        - Cache headers for optimal performance
        """,
        tags=["Stickers"],
        responses={
            200: {
                "description": "Sticker file content",
                "headers": {
                    "X-File-ID": {"description": "The file ID"},
                    "X-Is-Converted": {"description": "Whether the file was converted"},
                    "X-File-Size": {"description": "File size in bytes"},
                    "X-Processing-Time-Ms": {"description": "Processing time in milliseconds"},
                    "Cache-Control": {"description": "Cache control headers"}
                }
            },
            404: {"description": "Sticker not found"},
            429: {"description": "Rate limited"},
            500: {"description": "Internal server error"}
        }
    )
    async def get_sticker(file_id: str):
        """Get sticker file by file_id with multi-level caching and adaptive retry."""
        return await handler.get_sticker(file_id)
    
    return router

