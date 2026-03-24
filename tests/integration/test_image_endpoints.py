"""Integration tests for image upload endpoints."""
import io

import pytest
from PIL import Image

from app.main import cache_manager


def _png_payload() -> bytes:
    image = Image.new("RGB", (300, 200), color=(200, 80, 40))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_images_endpoint(client, monkeypatch):
    async def _fake_get_uploaded_image(_image_id):
        return None

    async def _fake_store_uploaded_image(**kwargs):
        assert kwargs["image_id"].startswith("img_")
        return True

    monkeypatch.setattr(cache_manager, "get_uploaded_image", _fake_get_uploaded_image)
    monkeypatch.setattr(cache_manager, "store_uploaded_image", _fake_store_uploaded_image)

    files = [("files", ("test.png", _png_payload(), "image/png"))]
    response = await client.post("/images/upload", files=files)

    assert response.status_code == 201
    body = response.json()
    assert "items" in body
    assert body["items"][0]["image_id"].startswith("img_")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_image_endpoint(client, monkeypatch):
    async def _fake_get_uploaded_image(_image_id):
        return b"sample-bytes", "image/png"

    monkeypatch.setattr(cache_manager, "get_uploaded_image", _fake_get_uploaded_image)
    response = await client.get("/images/img_test123")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
