"""Unit tests for cache manager service."""
import pytest
import allure
from unittest.mock import AsyncMock, Mock, patch
from app.services.cache_manager import CacheManager
from app.models.responses import StickerCache
from datetime import datetime


@allure.feature("Cache Manager")
@allure.tag("cache", "manager", "unit")
@pytest.mark.unit
class TestCacheManager:
    """Test CacheManager functionality."""
    
    @allure.title("Cache manager initialization")
    @allure.description("Test that cache manager initializes with all required services")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_manager_initialization(self, cache_manager):
        """Test cache manager initializes correctly."""
        with allure.step("Check cache manager instance"):
            assert cache_manager is not None
            assert hasattr(cache_manager, 'redis_service')
            assert hasattr(cache_manager, 'disk_cache_service')
            assert hasattr(cache_manager, 'telegram_service')
            assert hasattr(cache_manager, 'converter_service')
            assert hasattr(cache_manager, 'cache_strategy')
        
        with allure.step("Verify statistics initialization"):
            assert cache_manager.stats['total_requests'] == 0
            assert cache_manager.stats['redis_hits'] == 0
            assert cache_manager.stats['disk_hits'] == 0
    
    @allure.title("Get sticker from Redis cache")
    @allure.description("Test that stickers are retrieved from Redis cache when available")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_sticker_from_redis(self, cache_manager, create_test_cache_entry):
        """Test getting sticker from Redis cache."""
        file_id = "test_redis_file"
        cache_entry = create_test_cache_entry(
            file_id=file_id,
            file_data=b"redis_content",
            output_format="lottie"
        )
        
        with allure.step("Store sticker in Redis"):
            await cache_manager.redis_service.set_sticker(cache_entry)
        
        with allure.step("Retrieve sticker from cache"):
            result = await cache_manager.get_sticker(file_id)
            assert result is not None
            content, mime_type, was_converted = result
            assert content == b"redis_content"
            assert mime_type == "application/json"
            assert was_converted is True
        
        with allure.step("Verify Redis hit statistics"):
            assert cache_manager.stats['redis_hits'] == 1
            assert cache_manager.stats['total_requests'] == 1
    
    @allure.title("Get sticker from disk cache")
    @allure.description("Test that stickers are retrieved from disk cache when Redis miss")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_sticker_from_disk(self, cache_manager):
        """Test getting sticker from disk cache."""
        file_id = "test_disk_file"
        file_content = b"disk_content"
        
        with allure.step("Store file in disk cache"):
            await cache_manager.disk_cache_service.store_file(
                file_id, file_content, "lottie", converted=True
            )
        
        with allure.step("Retrieve sticker from disk cache"):
            result = await cache_manager.get_sticker(file_id)
            assert result is not None
            content, mime_type, was_converted = result
            assert content == file_content
            assert was_converted is True
        
        with allure.step("Verify disk hit statistics"):
            assert cache_manager.stats['disk_hits'] == 1
    
    @allure.title("Get sticker from Telegram API")
    @allure.description("Test that stickers are fetched from Telegram API when cache miss")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_sticker_from_telegram(self, cache_manager, sample_tgs_content):
        """Test getting sticker from Telegram API."""
        file_id = "test_telegram_file"
        file_path = "stickers/test.tgs"
        
        with allure.step("Mock Telegram API responses"):
            cache_manager.telegram_service.get_file_info = AsyncMock(return_value={
                'file_path': file_path,
                'file_size': len(sample_tgs_content)
            })
            cache_manager.telegram_service.download_file = AsyncMock(return_value=sample_tgs_content)
            cache_manager.telegram_service.detect_file_format = Mock(return_value='tgs')
            cache_manager.converter_service.convert_tgs_to_lottie = AsyncMock(return_value=(
                'lottie', b'{"v":"5.5.7"}'
            ))
        
        with allure.step("Retrieve sticker from Telegram"):
            result = await cache_manager.get_sticker(file_id)
            assert result is not None
            content, mime_type, was_converted = result
            assert was_converted is True
        
        with allure.step("Verify Telegram API call statistics"):
            assert cache_manager.stats['telegram_api_calls'] == 1
            assert cache_manager.stats['conversions_performed'] == 1
    
    @allure.title("Multi-level cache fallback")
    @allure.description("Test that cache manager falls back through levels correctly")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_multi_level_cache_fallback(self, cache_manager):
        """Test multi-level cache fallback."""
        file_id = "test_fallback_file"
        
        with allure.step("Redis miss, disk miss, fetch from Telegram"):
            # Mock Telegram API
            cache_manager.telegram_service.get_file_info = AsyncMock(return_value={
                'file_path': 'stickers/test.webp',
                'file_size': 1000
            })
            cache_manager.telegram_service.download_file = AsyncMock(return_value=b"webp_content")
            cache_manager.telegram_service.detect_file_format = Mock(return_value='webp')
        
        with allure.step("Get sticker (should fetch from Telegram)"):
            result = await cache_manager.get_sticker(file_id)
            assert result is not None
        
        with allure.step("Verify statistics"):
            assert cache_manager.stats['redis_misses'] >= 1
            assert cache_manager.stats['disk_misses'] >= 1
            assert cache_manager.stats['telegram_api_calls'] == 1
    
    @allure.title("Clear all cache")
    @allure.description("Test clearing all cache entries")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_clear_all_cache(self, cache_manager, create_test_cache_entry):
        """Test clearing all cache."""
        with allure.step("Store files in cache"):
            for i in range(3):
                entry = create_test_cache_entry(file_id=f"clear_test_{i}")
                await cache_manager.redis_service.set_sticker(entry)
                await cache_manager.disk_cache_service.store_file(
                    f"clear_test_{i}", b"content", "lottie"
                )
        
        with allure.step("Clear all cache"):
            results = await cache_manager.clear_all_cache()
            assert results is not None
        
        with allure.step("Verify files are cleared"):
            for i in range(3):
                redis_result = await cache_manager.redis_service.get_sticker(f"clear_test_{i}")
                assert redis_result is None
    
    @allure.title("Cleanup cache")
    @allure.description("Test cleanup of expired cache entries")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cleanup_cache(self, cache_manager):
        """Test cache cleanup."""
        with allure.step("Run cleanup"):
            results = await cache_manager.cleanup_cache()
            assert results is not None
            assert 'redis' in results or 'disk' in results
    
    @allure.title("Get cache statistics")
    @allure.description("Test getting comprehensive cache statistics")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, cache_manager):
        """Test getting cache statistics."""
        with allure.step("Get cache statistics"):
            stats = await cache_manager.get_cache_stats()
            assert stats is not None
            assert 'total_files' in stats or 'conversions_performed' in stats

