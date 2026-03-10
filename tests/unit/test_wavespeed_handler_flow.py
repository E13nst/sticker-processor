"""Unit tests for WaveSpeed flow in StickerHandler."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.handlers.sticker_handler import StickerHandler
from app.models.requests import WaveSpeedGenerateRequest, WaveSpeedSaveToSetRequest


@pytest.fixture
def mock_cache_manager():
    manager = Mock()
    manager.get_sticker_from_cache_only = AsyncMock(return_value=None)
    manager.store_generated_sticker = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def handler(mock_cache_manager):
    return StickerHandler(mock_cache_manager)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_wavespeed_returns_accepted(handler):
    handler._wavespeed_service = Mock()
    handler._wavespeed_service.submit = AsyncMock(return_value="provider-id-1")
    handler._wavespeed_service.client = Mock()
    handler._wavespeed_service.client.download_image = AsyncMock(return_value=b"")
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.create_job = AsyncMock()

    request = WaveSpeedGenerateRequest(prompt="hi", model="flux-schnell")
    response = await handler.generate_wavespeed_sticker(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_wavespeed_with_source_image_url(handler):
    handler._wavespeed_service = Mock()
    handler._wavespeed_service.submit = AsyncMock(return_value="provider-id-2")
    handler._wavespeed_service.client = Mock()
    handler._wavespeed_service.client.download_image = AsyncMock(return_value=b"raw-image-bytes")
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.create_job = AsyncMock()

    request = WaveSpeedGenerateRequest(
        prompt="hi",
        model="flux-schnell",
        source_image_url="https://example.com/image.png",
    )
    response = await handler.generate_wavespeed_sticker(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert handler._wavespeed_service.client.download_image.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_nanabanana_with_source_image_url_no_download(handler):
    handler._wavespeed_service = Mock()
    handler._wavespeed_service.submit = AsyncMock(return_value="provider-id-3")
    handler._wavespeed_service.client = Mock()
    handler._wavespeed_service.client.download_image = AsyncMock(return_value=b"raw-image-bytes")
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.create_job = AsyncMock()

    request = WaveSpeedGenerateRequest(
        prompt="hi",
        model="nanabanana",
        source_image_url="https://example.com/image.png",
    )
    response = await handler.generate_wavespeed_sticker(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert handler._wavespeed_service.client.download_image.await_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_nanabanana_text_to_image_no_source(handler):
    handler._wavespeed_service = Mock()
    handler._wavespeed_service.submit = AsyncMock(return_value="provider-id-4")
    handler._wavespeed_service.client = Mock()
    handler._wavespeed_service.client.download_image = AsyncMock(return_value=b"raw-image-bytes")
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.create_job = AsyncMock()

    request = WaveSpeedGenerateRequest(
        prompt="fat gold cat with rick and morty",
        model="nanabanana",
    )
    response = await handler.generate_wavespeed_sticker(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    handler._wavespeed_service.submit.assert_awaited_once()
    kwargs = handler._wavespeed_service.submit.await_args.kwargs
    assert kwargs["image"] == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_wavespeed_pending(handler):
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.get_job = AsyncMock(return_value={
        "file_id": "ws_123",
        "status": "pending",
        "provider_request_id": "req-1",
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
    })
    handler._refresh_wavespeed_job_status = AsyncMock(return_value="pending")

    response = await handler.get_wavespeed_sticker("ws_123")
    assert isinstance(response, JSONResponse)
    assert response.status_code == 202


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_wavespeed_failed_maps_error(handler):
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.get_job = AsyncMock(side_effect=[
        {
            "file_id": "ws_123",
            "status": "pending",
            "provider_request_id": "req-1",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        },
        {
            "file_id": "ws_123",
            "status": "failed",
            "error_payload": {"code": "generation_failed", "message": "boom"},
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        },
    ])
    handler._refresh_wavespeed_job_status = AsyncMock(return_value="failed")

    with pytest.raises(HTTPException) as exc:
        await handler.get_wavespeed_sticker("ws_123")
    assert exc.value.status_code == 424


@pytest.mark.unit
@pytest.mark.asyncio
async def test_materialize_remove_background_success(handler):
    handler.cache_manager.get_sticker_from_cache_only = AsyncMock(side_effect=[None, None])
    handler.cache_manager.store_generated_sticker = AsyncMock(return_value=True)

    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.get_job = AsyncMock(return_value={
        "file_id": "ws_123",
        "status": "completed",
        "source_url": "http://img",
        "remove_background": True,
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
    })
    handler._wavespeed_registry.set_ready = AsyncMock()

    service = Mock()
    service.client = Mock()
    service.client.download_image = AsyncMock(side_effect=[b"original", b"bg"])
    service.client.submit_background_remover = AsyncMock(return_value="bg-req")
    service.poll_until_terminal = AsyncMock(return_value={"status": "completed", "outputs": ["http://bg"]})
    service.extract_status = Mock(return_value="completed")
    service.extract_output_url = Mock(return_value="http://bg")
    handler._wavespeed_service = service

    handler._sticker_normalizer = Mock()
    handler._sticker_normalizer.normalize_to_webp = Mock(return_value=(b"webp", "image/webp"))

    content, mime = await handler._materialize_wavespeed_job("ws_123")
    assert content == b"webp"
    assert mime == "image/webp"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_materialize_remove_background_failure(handler):
    handler.cache_manager.get_sticker_from_cache_only = AsyncMock(side_effect=[None, None])
    handler._wavespeed_registry = Mock()
    handler._wavespeed_registry.get_job = AsyncMock(return_value={
        "file_id": "ws_124",
        "status": "completed",
        "source_url": "http://img",
        "remove_background": True,
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
    })
    handler._wavespeed_registry.set_failed = AsyncMock()

    service = Mock()
    service.client = Mock()
    service.client.download_image = AsyncMock(return_value=b"original")
    service.client.submit_background_remover = AsyncMock(return_value="bg-req")
    service.poll_until_terminal = AsyncMock(return_value={"status": "failed", "error": "remover error"})
    service.extract_status = Mock(return_value="failed")
    service.extract_error = Mock(return_value="remover error")
    handler._wavespeed_service = service

    with pytest.raises(HTTPException) as exc:
        await handler._materialize_wavespeed_job("ws_124")
    assert exc.value.status_code == 424


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_wavespeed_sticker_to_set_success(handler):
    handler._await_wavespeed_sticker_ready = AsyncMock(return_value=(b"webp-bytes", "image/webp"))
    handler.cache_manager.telegram_service = Mock()
    handler.cache_manager.telegram_service.save_sticker_to_set = AsyncMock(
        return_value={"action": "added", "name": "my_set_by_bot"}
    )

    request = WaveSpeedSaveToSetRequest(
        file_id="ws_123",
        user_id=12345,
        name="my_set_by_bot",
        title="My Set",
        emoji="😀",
    )
    response = await handler.save_wavespeed_sticker_to_set(request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    handler.cache_manager.telegram_service.save_sticker_to_set.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_wavespeed_sticker_to_set_unsupported_format(handler):
    handler._await_wavespeed_sticker_ready = AsyncMock(return_value=(b"png-bytes", "image/png"))

    request = WaveSpeedSaveToSetRequest(
        file_id="ws_123",
        user_id=12345,
        name="my_set_by_bot",
        title="My Set",
        emoji="😀",
    )
    with pytest.raises(HTTPException) as exc:
        await handler.save_wavespeed_sticker_to_set(request)
    assert exc.value.status_code == 422
