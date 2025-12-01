"""Pytest configuration and fixtures."""
import os
import sys
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
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
from app.services.cache_manager import CacheManager
from app.services.cache_strategy import CacheStrategy
from app.services.disk_cache import DiskCacheService
from app.services.telegram_queue import TelegramRequestQueue
from app.middleware.rate_limit import RateLimitMiddleware

# Allure integration
try:
    import allure
    ALLURE_AVAILABLE = True
except ImportError:
    ALLURE_AVAILABLE = False
    # Create a mock allure module for when it's not installed
    class MockAllure:
        @staticmethod
        def step(text):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def title(text):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def description(text):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def severity(level):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def tag(*tags):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def feature(feature):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def story(story):
            def decorator(func):
                return func
            return decorator
        
        class attachment_type:
            JSON = "application/json"
            TEXT = "text/plain"
        
        @staticmethod
        def attach(body, name, attachment_type):
            pass
        
        class Severity:
            BLOCKER = "blocker"
            CRITICAL = "critical"
            NORMAL = "normal"
            MINOR = "minor"
            TRIVIAL = "trivial"
        
        severity_level = Severity
    
    allure = MockAllure()


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
    from httpx import Timeout
    timeout = Timeout(120.0, connect=10.0)  # 120s total, 10s connect timeout
    async with AsyncClient(app=app, base_url="http://test", timeout=timeout) as ac:
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


@pytest.fixture
def cache_strategy() -> CacheStrategy:
    """Cache strategy service instance."""
    return CacheStrategy()


@pytest.fixture
def temp_cache_dir() -> Generator[Path, None, None]:
    """Temporary directory for disk cache tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_disk_cache_"))
    yield temp_dir
    # Cleanup
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def disk_cache_service(temp_cache_dir: Path, monkeypatch) -> DiskCacheService:
    """Disk cache service instance with temporary directory."""
    # Override cache directory for testing using monkeypatch
    from app.config import settings
    original_dir = settings.disk_cache_dir
    monkeypatch.setattr(settings, "disk_cache_dir", str(temp_cache_dir))
    
    # Create new service instance with patched settings
    service = DiskCacheService()
    
    # Verify it uses the temp directory
    assert service.cache_dir == temp_cache_dir
    
    yield service
    
    # Restore original (though monkeypatch should handle this)
    monkeypatch.setattr(settings, "disk_cache_dir", original_dir)


@pytest.fixture
async def telegram_queue() -> AsyncGenerator[TelegramRequestQueue, None]:
    """Telegram request queue instance with proper cleanup."""
    queue = TelegramRequestQueue(max_concurrent=2, delay_ms=50, adaptive=True)
    yield queue
    # Cleanup: shutdown queue processor to prevent warnings
    if queue._running:
        await queue.shutdown()


@pytest.fixture
async def cache_manager(fake_redis_service, temp_cache_dir: Path) -> AsyncGenerator[CacheManager, None]:
    """Cache manager instance for unit tests."""
    # Override cache directory for testing
    original_dir = os.environ.get("DISK_CACHE_DIR")
    os.environ["DISK_CACHE_DIR"] = str(temp_cache_dir)
    
    manager = CacheManager()
    # Replace Redis service with fake one
    manager.redis_service = fake_redis_service
    
    yield manager
    
    # Cleanup
    await manager.disconnect()
    
    # Restore original setting
    if original_dir:
        os.environ["DISK_CACHE_DIR"] = original_dir
    elif "DISK_CACHE_DIR" in os.environ:
        del os.environ["DISK_CACHE_DIR"]


@pytest.fixture
def rate_limit_middleware(app: FastAPI) -> RateLimitMiddleware:
    """Rate limit middleware instance for testing."""
    return RateLimitMiddleware(app, enabled=True)


# =============================================================================
# Fake Redis Fixture (for unit tests)
# =============================================================================

@pytest.fixture
async def fake_redis_service() -> AsyncGenerator[RedisService, None]:
    """Fake Redis service using fakeredis (for unit tests)."""
    try:
        from fakeredis.aioredis import FakeRedis
    except ImportError:
        pytest.skip("fakeredis not installed")
    
    service = RedisService()
    # Create fake Redis server and client
    fake_server = FakeRedis(decode_responses=False)
    # Use the server directly as the redis client
    service.redis = fake_server
    yield service
    # Cleanup
    try:
        await fake_server.close()
    except Exception:
        pass


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


# =============================================================================
# Allure Hooks
# =============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach test results to Allure."""
    outcome = yield
    rep = outcome.get_result()
    
    if ALLURE_AVAILABLE and rep.when == "call":
        if rep.failed:
            # Attach error details
            if hasattr(rep, "longrepr") and rep.longrepr:
                allure.attach(
                    str(rep.longrepr),
                    name="Test Failure",
                    attachment_type=allure.attachment_type.TEXT
                )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Log test setup in Allure."""
    if ALLURE_AVAILABLE:
        # Attach test configuration
        config_info = {
            "test_name": item.name,
            "test_file": str(item.fspath),
            "markers": [mark.name for mark in item.iter_markers()],
        }
        allure.attach(
            str(config_info),
            name="Test Configuration",
            attachment_type=allure.attachment_type.JSON
        )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Configure Allure environment."""
    if ALLURE_AVAILABLE:
        # Create allure-results directory if it doesn't exist
        allure_dir = Path("allure-results")
        allure_dir.mkdir(exist_ok=True)
        
        # Attach environment information
        env_info = {
            "python_version": sys.version,
            "pytest_version": pytest.__version__,
            "test_path": str(Path.cwd()),
        }
        allure.attach(
            str(env_info),
            name="Environment",
            attachment_type=allure.attachment_type.JSON
        )

