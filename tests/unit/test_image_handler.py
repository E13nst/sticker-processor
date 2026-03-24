"""Unit tests for image upload handler."""
import io
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image

from app.handlers.image_handler import ImageHandler


def _build_png_bytes() -> bytes:
    image = Image.new("RGB", (256, 256), color=(120, 30, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_images_returns_image_id(monkeypatch):
    cache_manager = Mock()
    cache_manager.get_uploaded_image = AsyncMock(return_value=None)
    cache_manager.store_uploaded_image = AsyncMock(return_value=True)
    handler = ImageHandler(cache_manager)

    file = UploadFile(filename="test.png", file=io.BytesIO(_build_png_bytes()))
    response = await handler.upload_images([file])

    assert isinstance(response, JSONResponse)
    assert response.status_code == 201
    assert b'"image_id":"img_' in response.body
    cache_manager.store_uploaded_image.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_image_from_cache():
    cache_manager = Mock()
    cache_manager.get_uploaded_image = AsyncMock(return_value=(b"image-bytes", "image/png"))
    handler = ImageHandler(cache_manager)

    response = await handler.get_image("img_test")
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "image/png"
