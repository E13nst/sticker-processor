"""Handler for uploaded image operations."""
import hashlib
import io
from datetime import datetime, timedelta
from typing import List

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.models.responses import ImageUploadItem
from app.services.cache_manager import CacheManager
from app.services.image_transformer import ImageTransformer


class ImageHandler:
    """Business logic for uploading and reading image assets."""

    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
        self.transformer = ImageTransformer()

    async def upload_images(self, files: List[UploadFile]) -> JSONResponse:
        """Upload one or many images and store normalized payload in Redis."""
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required")
        if len(files) > settings.image_upload_max_files_per_request:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files. Maximum is {settings.image_upload_max_files_per_request}",
            )

        items: List[ImageUploadItem] = []
        for file in files:
            raw_bytes = await file.read()
            if not raw_bytes:
                raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")

            max_size_bytes = settings.image_upload_max_file_size_mb * 1024 * 1024
            if len(raw_bytes) > max_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{file.filename}' exceeds {settings.image_upload_max_file_size_mb}MB limit",
                )

            try:
                normalized_bytes, mime_type, output_format = self.transformer.normalize_for_nanabanana(raw_bytes)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid image '{file.filename}': {exc}") from exc

            image_id = self._build_image_id(normalized_bytes)
            deduplicated = False
            existing = await self.cache_manager.get_uploaded_image(image_id)
            if existing is None:
                stored = await self.cache_manager.store_uploaded_image(
                    image_id=image_id,
                    content=normalized_bytes,
                    output_format=output_format,
                    mime_type=mime_type,
                )
                if not stored:
                    raise HTTPException(status_code=503, detail="Failed to store image in Redis cache")
            else:
                deduplicated = True

            expires_at = datetime.utcnow() + timedelta(days=settings.image_cache_ttl_days)
            items.append(
                ImageUploadItem(
                    image_id=image_id,
                    mime_type=mime_type,
                    file_size=len(normalized_bytes),
                    expires_at=expires_at,
                    deduplicated=deduplicated,
                )
            )

        return JSONResponse(
            status_code=201,
            content={"items": [item.model_dump(mode="json") for item in items]},
        )

    async def get_image(self, image_id: str) -> StreamingResponse:
        """Return normalized image bytes by id from Redis."""
        cached = await self.cache_manager.get_uploaded_image(image_id)
        if not cached:
            raise HTTPException(status_code=404, detail="Image not found")

        content, mime_type = cached
        return StreamingResponse(io.BytesIO(content), media_type=mime_type)

    @staticmethod
    def _build_image_id(content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()[:24]
        return f"img_{digest}"
