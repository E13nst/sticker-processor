"""Sticker routes."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.cache_manager import CacheManager
from app.handlers.sticker_handler import StickerHandler
from app.models.requests import CombineStickersRequest


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
    
    @router.post(
        "/stickers/combine",
        response_class=StreamingResponse,
        summary="Combine Stickers",
        description="""
        Combine multiple stickers into a single grid image optimized for LLM vision models.
        
        **Features:**
        - Downloads and caches all stickers using multi-level caching
        - Resizes each image to square tiles (default 128x128) with preserved aspect ratio
        - Arranges images in a grid layout close to square
        - Returns combined image in WebP format
        - Skips failed files (errors only if all files fail)
        
        **Image Processing:**
        - Images are resized maintaining aspect ratio
        - Non-square images are centered on square canvas with white background
        - Only image formats are processed (TGS/Lottie JSON and WebM are skipped)
        """,
        tags=["Stickers"],
        responses={
            200: {
                "description": "Combined WebP image",
                "headers": {
                    "X-Processing-Time-Ms": {"description": "Processing time in milliseconds"},
                    "X-Images-Combined": {"description": "Number of images successfully combined"},
                    "X-Images-Failed": {"description": "Number of images that failed to load"},
                    "X-Tile-Size": {"description": "Size of each tile in pixels"},
                    "Content-Type": {"description": "image/webp"}
                }
            },
            400: {"description": "Bad request (empty file_ids list)"},
            404: {"description": "No images could be retrieved from provided file_ids"},
            500: {"description": "Internal server error"}
        }
    )
    async def combine_stickers(request: CombineStickersRequest):
        """Combine multiple stickers into a single grid image."""
        return await handler.combine_stickers(
            file_ids=request.file_ids,
            tile_size=request.tile_size
        )
    
    return router

