"""Image upload and retrieval routes."""
from typing import List

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.handlers.image_handler import ImageHandler
from app.services.cache_manager import CacheManager


def create_images_router(cache_manager: CacheManager) -> APIRouter:
    """Create images router with cache manager dependency."""
    router = APIRouter()
    handler = ImageHandler(cache_manager)

    @router.post(
        "/images/upload",
        summary="Upload Source Images",
        description=(
            "Upload one or many source images via multipart/form-data and store normalized versions in Redis. "
            "Returns deterministic image IDs that can be used in WaveSpeed generation requests."
        ),
        tags=["Images"],
        status_code=201,
    )
    async def upload_images(files: List[UploadFile] = File(...)):
        """Upload image files for generation/editing workflows."""
        return await handler.upload_images(files)

    @router.get(
        "/images/{image_id}",
        response_class=StreamingResponse,
        summary="Get Uploaded Image",
        description="Get uploaded normalized image by image_id from Redis cache.",
        tags=["Images"],
    )
    async def get_image(image_id: str):
        """Get uploaded image by id."""
        return await handler.get_image(image_id)

    return router
