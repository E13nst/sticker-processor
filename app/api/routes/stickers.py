"""Sticker routes."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.cache_manager import CacheManager
from app.handlers.sticker_handler import StickerHandler
from app.models.requests import CombineStickersRequest, CombineStickerSetRequest, GenerateStickerRequest


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
    
    @router.post(
        "/stickers/combine-from-set",
        response_class=StreamingResponse,
        summary="Combine Stickers from Set",
        description="""
        Combine stickers from a Telegram sticker set into a single grid image.
        
        **Features:**
        - Accepts either sticker set name or URL (e.g., "https://t.me/addstickers/arcticfox")
        - Fetches sticker set metadata from Telegram Bot API (with Redis caching for 1 day)
        - Extracts images in the exact order they appear in the sticker set
        - Supports different image types:
          - "main" (default): Full-size sticker images
          - "thumbnail": Thumbnail images (128x128)
          - "thumb": Alternative thumb images
        - Downloads and caches all images using multi-level caching
        - Resizes each image to square tiles (default 128x128) with preserved aspect ratio
        - Arranges images in a grid layout close to square
        - Returns combined image in WebP format
        - Skips failed files (errors only if all files fail)
        - Supports limiting the number of stickers processed via `max_stickers` parameter
        
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
                    "X-Sticker-Set-Name": {"description": "Name of the sticker set"},
                    "X-Image-Type": {"description": "Type of images used (main/thumbnail/thumb)"},
                    "Content-Type": {"description": "image/webp"}
                }
            },
            400: {"description": "Bad request (missing name/url or invalid parameters)"},
            404: {"description": "Sticker set not found or no valid images in set"},
            500: {"description": "Internal server error"}
        }
    )
    async def combine_sticker_set(request: CombineStickerSetRequest):
        """Combine stickers from a sticker set into a single grid image."""
        return await handler.combine_sticker_set(
            name=request.name,
            image_type=request.image_type or "main",
            tile_size=request.tile_size,
            max_stickers=request.max_stickers
        )
    
    @router.post(
        "/stickers/generate",
        response_class=StreamingResponse,
        summary="Generate Sticker",
        description="""
        Generate a Telegram sticker image using OpenAI API (model: gpt-image-1) based on a text prompt.
        
        **Features:**
        - Generates WebP images with transparent background
        - Configurable image size
        - Automatic scaling for Telegram sticker format (512x512)
        - Optimized for Telegram sticker format
        
        **Parameters:**
        - `prompt`: Text description of the sticker to generate (required)
        - `quality`: Deprecated - kept for backward compatibility, but not used by API
        - `size`: Image size (default: "512x512")
        
        **Supported Sizes:**
        - `"512x512"` - Telegram sticker size (generated at 1024x1024, then scaled down)
        - `"1024x1024"` - Square high resolution
        - `"1024x1536"` - Portrait orientation
        - `"1536x1024"` - Landscape orientation
        - `"auto"` - Let OpenAI choose the best size
        
        **Note:** 
        - The `quality` parameter is accepted but ignored by the API. Model gpt-image-1 doesn't support quality parameter.
        - Size `512x512` is automatically generated at `1024x1024` and scaled down to maintain quality.
        
        **Response:**
        - Returns WebP image with transparent background
        - Headers include processing time and image size
        """,
        tags=["Stickers"],
        responses={
            200: {
                "description": "Generated WebP sticker image",
                "headers": {
                    "X-Processing-Time-Ms": {"description": "Processing time in milliseconds"},
                    "X-Image-Size": {"description": "Image size in bytes"},
                    "Content-Type": {"description": "image/webp"}
                }
            },
            400: {"description": "Bad request (invalid prompt, quality, or size)"},
            500: {"description": "Internal server error (OpenAI API error)"}
        }
    )
    async def generate_sticker(request: GenerateStickerRequest):
        """Generate a sticker image using OpenAI API."""
        return await handler.generate_sticker(request)
    
    return router

