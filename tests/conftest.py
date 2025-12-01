"""Pytest configuration and fixtures."""
import os
import sys
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from fastapi import FastAPI

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import Settings
from app.main import app as fastapi_app
from app.services.redis import RedisService
from app.services.telegram_enhanced import TelegramServiceEnhanced
from app.services.converter import ConverterService


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings - loads from .env for integration tests."""
    # Load .env file if it exists (for integration tests with production Redis)
    from dotenv import load_dotenv
    load_dotenv()
    
    # Only set defaults that are safe for testing
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "test_bot_token"))
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    
    # For integration tests, use production Redis settings from .env
    # For unit tests, these won't be used anyway
    
    from app.config import Settings
    return Settings()


# =============================================================================
# App Fixtures
# =============================================================================

@pytest.fixture
def app() -> FastAPI:
    """FastAPI application instance."""
    return fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Service Fixtures
# =============================================================================

@pytest.fixture
async def redis_service(test_settings) -> AsyncGenerator[RedisService, None]:
    """Redis service instance for integration tests."""
    service = RedisService()
    try:
        await service.connect()
        yield service
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")
    finally:
        await service.disconnect()


@pytest.fixture
def telegram_service() -> TelegramServiceEnhanced:
    """Telegram service instance."""
    return TelegramServiceEnhanced()


@pytest.fixture
def converter_service() -> ConverterService:
    """Converter service instance."""
    return ConverterService()


# =============================================================================
# Fake Redis Fixture (for unit tests)
# =============================================================================

@pytest.fixture
async def fake_redis_service() -> AsyncGenerator[RedisService, None]:
    """Fake Redis service using fakeredis (for unit tests)."""
    try:
        import fakeredis.aioredis as fakeredis
    except ImportError:
        pytest.skip("fakeredis not installed")
    
    service = RedisService()
    # Replace real Redis with fake one
    service.redis = fakeredis.FakeRedis(decode_responses=False)
    yield service
    await service.redis.close()


# =============================================================================
# Mock Data Fixtures
# =============================================================================

@pytest.fixture
def sample_tgs_content() -> bytes:
    """Sample TGS (gzipped JSON) content for testing."""
    import gzip
    import json
    
    lottie_data = {
        "v": "5.5.7",
        "fr": 60,
        "ip": 0,
        "op": 180,
        "w": 512,
        "h": 512,
        "nm": "Test Animation",
        "ddd": 0,
        "assets": [],
        "layers": []
    }
    
    return gzip.compress(json.dumps(lottie_data).encode('utf-8'))


@pytest.fixture
def sample_file_id() -> str:
    """Sample Telegram file_id for testing."""
    return "CAACAgIAAxUAAWdVqJ_sample_file_id_for_testing"


@pytest.fixture
def telegram_file_info_response() -> dict:
    """Sample Telegram getFile API response."""
    return {
        "ok": True,
        "result": {
            "file_id": "CAACAgIAAxUAAWdVqJ_test",
            "file_unique_id": "AgADfAADTest",
            "file_size": 12345,
            "file_path": "stickers/file_0.webp"
        }
    }


# =============================================================================
# Helper Functions
# =============================================================================

@pytest.fixture
def create_test_cache_entry():
    """Helper to create test cache entries."""
    from app.models.responses import StickerCache
    from datetime import datetime
    
    def _create(
        file_id: str = "test_file_id",
        file_data: bytes = b"test_data",
        output_format: str = "lottie"
    ) -> StickerCache:
        return StickerCache(
            file_id=file_id,
            file_data=file_data,
            mime_type="application/json",
            file_name=f"{file_id}.{output_format}",
            file_size=len(file_data),
            original_format="tgs",
            output_format=output_format,
            telegram_file_path="stickers/test.tgs",
            last_updated=datetime.now(),
            conversion_time_ms=150,
            is_converted=True
        )
    
    return _create


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest.fixture
async def cleanup_redis_test_data(redis_service):
    """Cleanup Redis test data after integration tests.
    
    Note: This is NOT autouse - only integration tests should use this.
    """
    yield
    # Cleanup test keys after test
    try:
        if redis_service.redis:
            test_keys = await redis_service.redis.keys("sticker:file:test_*")
            if test_keys:
                await redis_service.redis.delete(*test_keys)
    except Exception:
        pass  # Redis might not be available


# =============================================================================
# Event Loop Configuration
# =============================================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy for tests."""
    return asyncio.get_event_loop_policy()

