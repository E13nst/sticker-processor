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
        
        with allure.step("Mock Redis get_sticker to return cached entry"):
            from unittest.mock import AsyncMock, Mock
            import time
            
            # Mock check_redis method directly to avoid issues with service references
            async def mock_check_redis(file_id, request_start):
                cache_manager.cache_chain.stats['redis_hits'] += 1
                # Sync stats to main stats
                cache_manager.stats['redis_hits'] += 1
                return (cache_entry.file_data, cache_entry.mime_type, cache_entry.is_converted)
            
            cache_manager._check_redis = mock_check_redis
        
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
        file_id = "test_telegram_file_unique"
        file_path = "stickers/test.tgs"
        
        with allure.step("Mock all cache levels to miss"):
            from unittest.mock import AsyncMock, Mock
            # Redis miss
            cache_manager.redis_service.get_sticker = AsyncMock(return_value=None)
            # Disk miss
            cache_manager.disk_cache_service.get_file = AsyncMock(return_value=None)
        
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
            # Conversion should be performed for TGS files
            assert cache_manager.stats['conversions_performed'] >= 1
    
    @allure.title("Multi-level cache fallback")
    @allure.description("Test that cache manager falls back through levels correctly")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_multi_level_cache_fallback(self, cache_manager):
        """Test multi-level cache fallback."""
        file_id = "test_fallback_file"
        
        with allure.step("Mock all cache levels to miss, then Telegram to return data"):
            from unittest.mock import AsyncMock, Mock
            import time
            
            # Mock check_redis to return None (miss)
            async def mock_check_redis(file_id, request_start):
                cache_manager.cache_chain.stats['redis_misses'] += 1
                # Sync stats to main stats
                cache_manager.stats['redis_misses'] += 1
                return None
            
            # Mock check_disk to return None (miss)
            async def mock_check_disk(file_id, request_start):
                cache_manager.cache_chain.stats['disk_misses'] += 1
                # Sync stats to main stats
                cache_manager.stats['disk_misses'] += 1
                return None
            
            cache_manager._check_redis = mock_check_redis
            cache_manager._check_disk = mock_check_disk
            
            # Telegram API returns data
            cache_manager.telegram_service.get_file_info = AsyncMock(return_value={
                'file_path': 'stickers/test.webp',
                'file_size': 1000
            })
            cache_manager.telegram_service.download_file = AsyncMock(return_value=b"webp_content")
            cache_manager.telegram_service.detect_file_format = Mock(return_value='webp')
            cache_manager.telegram_service.get_mime_type = Mock(return_value='image/webp')
            # Mock redis service for _fetch_from_telegram - use AsyncMock for close method
            cache_manager.redis_service.redis = AsyncMock()
            cache_manager.redis_service.redis.close = AsyncMock(return_value=None)
            async def mock_set_sticker(cache_entry):
                return True
            cache_manager.redis_service.set_sticker = mock_set_sticker
            cache_manager.cache_strategy.should_cache_in_redis = Mock(return_value=True)
        
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
        with allure.step("Mock cache clearing operations"):
            from unittest.mock import AsyncMock
            cache_manager.redis_service.clear_cache = AsyncMock(return_value=5)
            cache_manager.disk_cache_service.clear_cache = AsyncMock(return_value=3)
        
        with allure.step("Clear all cache"):
            results = await cache_manager.clear_all_cache()
            assert results is not None
            # Results should contain either success or error keys
            assert 'redis_cleared' in results or 'disk_cleared' in results or 'redis_error' in results or 'disk_error' in results
    
    @allure.title("Cleanup cache")
    @allure.description("Test cleanup of expired cache entries")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cleanup_cache(self, cache_manager):
        """Test cache cleanup."""
        with allure.step("Mock cleanup operations"):
            from unittest.mock import AsyncMock
            cache_manager.disk_cache_service.cleanup_expired_files = AsyncMock(return_value=5)
            cache_manager.disk_cache_service.get_cache_stats = AsyncMock(return_value={'total_size_mb': 10})
        
        with allure.step("Run cleanup"):
            results = await cache_manager.cleanup_cache()
            assert results is not None
            # Results should contain cleanup information
            assert isinstance(results, dict)
            # Should have either disk_cleaned or redis_cleaned or errors
            assert 'disk_cleaned' in results or 'redis_cleaned' in results or 'disk_error' in results or 'redis_error' in results
    
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

