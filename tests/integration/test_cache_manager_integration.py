"""Integration tests for cache manager with real services."""
import pytest
import allure
import json
from app.services.cache_manager import CacheManager
from app.models.responses import StickerCache
from datetime import datetime


@allure.feature("Cache Manager Integration")
@allure.tag("cache", "manager", "integration")
@pytest.mark.integration
@pytest.mark.redis
class TestCacheManagerIntegration:
    """Test CacheManager with real services."""
    
    @allure.title("Cache manager initialization and connection")
    @allure.description("Test that cache manager connects to Redis successfully")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_cache_manager_connection(self, redis_service):
        """Test cache manager connection."""
        cache_manager = CacheManager()
        cache_manager.redis_service = redis_service
        
        with allure.step("Connect cache manager"):
            await cache_manager.connect()
            assert cache_manager.redis_service.redis is not None
        
        with allure.step("Disconnect cache manager"):
            await cache_manager.disconnect()
    
    @allure.title("Multi-level caching end-to-end")
    @allure.description("Test complete multi-level caching flow: Redis -> Disk -> Telegram")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_multi_level_caching(self, redis_service, temp_cache_dir, create_test_cache_entry):
        """Test multi-level caching flow."""
        import os
        os.environ["DISK_CACHE_DIR"] = str(temp_cache_dir)
        
        cache_manager = CacheManager()
        cache_manager.redis_service = redis_service
        
        file_id = "test_integration_file"
        cache_entry = create_test_cache_entry(
            file_id=file_id,
            file_data=b"integration_test_content",
            output_format="lottie"
        )
        
        with allure.step("Store file in Redis"):
            await cache_manager.redis_service.set_sticker(cache_entry)
        
        with allure.step("Retrieve from Redis (Level 1)"):
            result = await cache_manager.get_sticker(file_id)
            assert result is not None
            content, mime_type, was_converted = result
            assert content == b"integration_test_content"
            assert cache_manager.stats['redis_hits'] == 1
        
        with allure.step("Verify statistics"):
            stats = await cache_manager.get_cache_stats()
            allure.attach(json.dumps(stats, indent=2, default=str), "Cache Statistics", allure.attachment_type.JSON)
        
        await cache_manager.disconnect()
    
    @allure.title("Cache fallback between levels")
    @allure.description("Test that cache manager can retrieve files from disk cache when Redis miss")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.asyncio
    async def test_cache_fallback(self, redis_service, temp_cache_dir, monkeypatch):
        """Test cache fallback between levels - simplified version.
        
        Note: Full fallback testing is done in test_disk_cache_fallback.py.
        This test just verifies basic integration works.
        """
        from app.config import settings
        from app.services.disk_cache import DiskCacheService
        
        # Override disk cache directory using monkeypatch BEFORE creating CacheManager
        monkeypatch.setattr(settings, "disk_cache_dir", str(temp_cache_dir))
        
        # Create new cache manager with patched settings
        cache_manager = CacheManager()
        cache_manager.redis_service = redis_service
        # Recreate disk_cache_service with patched settings
        cache_manager.disk_cache_service = DiskCacheService()
        
        file_id = "test_fallback_simple"
        file_content = b"fallback_content"
        
        with allure.step("Store file in disk cache"):
            await cache_manager.disk_cache_service.store_file(
                file_id, file_content, "lottie", converted=True
            )
        
        with allure.step("Verify file can be retrieved from disk cache directly"):
            # Test direct disk cache access first
            direct_result = await cache_manager.disk_cache_service.get_file(file_id, "lottie")
            assert direct_result == file_content, "File should be retrievable from disk cache"
        
        with allure.step("Retrieve via cache manager (should find in disk cache)"):
            result = await cache_manager.get_sticker(file_id)
            # Just verify we get the content - statistics may vary
            assert result is not None, "Should retrieve file from disk cache"
            content, mime_type, was_converted = result
            assert content == file_content, "Content should match"
        
        await cache_manager.disconnect()
    
    @allure.title("Cache statistics in real conditions")
    @allure.description("Test that cache statistics are accurate in real usage")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_statistics_real(self, redis_service, temp_cache_dir, create_test_cache_entry):
        """Test cache statistics in real conditions."""
        import os
        os.environ["DISK_CACHE_DIR"] = str(temp_cache_dir)
        
        cache_manager = CacheManager()
        cache_manager.redis_service = redis_service
        
        with allure.step("Store multiple files"):
            for i in range(5):
                entry = create_test_cache_entry(
                    file_id=f"stats_test_{i}",
                    file_data=f"content_{i}".encode(),
                    output_format="lottie"
                )
                await cache_manager.redis_service.set_sticker(entry)
        
        with allure.step("Retrieve files to generate hits"):
            for i in range(5):
                await cache_manager.get_sticker(f"stats_test_{i}")
        
        with allure.step("Get and verify statistics"):
            stats = await cache_manager.get_cache_stats()
            allure.attach(json.dumps(stats, indent=2, default=str), "Real Cache Statistics", allure.attachment_type.JSON)
            
            assert cache_manager.stats['redis_hits'] >= 5
            assert cache_manager.stats['total_requests'] >= 5
        
        await cache_manager.disconnect()

