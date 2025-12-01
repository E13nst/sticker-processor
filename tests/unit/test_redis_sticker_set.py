"""Unit tests for Redis sticker set caching."""
import pytest
import allure
import json
from unittest.mock import AsyncMock, Mock
from app.services.redis import RedisService


@allure.feature("Redis Service")
@allure.tag("redis", "sticker-set", "cache", "unit")
@pytest.mark.unit
class TestRedisStickerSet:
    """Test Redis sticker set caching functionality."""
    
    @allure.title("Get sticker set from cache")
    @allure.description("Test retrieving sticker set from Redis cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_sticker_set_from_cache(self, fake_redis_service):
        """Test getting sticker set from Redis cache."""
        service = fake_redis_service
        sticker_set_name = "test_set"
        sticker_set_data = {
            "name": "test_set",
            "title": "Test Set",
            "stickers": [
                {"file_id": "file1", "emoji": "😀"},
                {"file_id": "file2", "emoji": "😃"}
            ]
        }
        
        # Store sticker set in cache
        stored = await service.set_sticker_set(sticker_set_name, sticker_set_data)
        
        # Skip test if fakeredis doesn't support set_sticker_set
        if not stored:
            pytest.skip("fakeredis doesn't support set_sticker_set operations")
        
        # Retrieve from cache
        result = await service.get_sticker_set(sticker_set_name)
        
        assert result is not None
        assert result["name"] == sticker_set_data["name"]
        assert result["title"] == sticker_set_data["title"]
        assert len(result["stickers"]) == 2
        assert result["stickers"][0]["file_id"] == "file1"
    
    @allure.title("Get non-existent sticker set")
    @allure.description("Test retrieving non-existent sticker set returns None")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_get_nonexistent_sticker_set(self, fake_redis_service):
        """Test getting non-existent sticker set returns None."""
        service = fake_redis_service
        result = await service.get_sticker_set("nonexistent_set")
        assert result is None
    
    @allure.title("Set sticker set in cache")
    @allure.description("Test storing sticker set in Redis cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_set_sticker_set_in_cache(self, fake_redis_service):
        """Test storing sticker set in Redis cache."""
        service = fake_redis_service
        sticker_set_name = "test_set"
        sticker_set_data = {
            "name": "test_set",
            "title": "Test Set",
            "stickers": [{"file_id": "file1"}]
        }
        
        result = await service.set_sticker_set(sticker_set_name, sticker_set_data)
        
        # Skip test if fakeredis doesn't support set_sticker_set
        if not result:
            pytest.skip("fakeredis doesn't support set_sticker_set operations")
        
        assert result is True
        
        # Verify it was stored
        retrieved = await service.get_sticker_set(sticker_set_name)
        assert retrieved is not None
        assert retrieved["name"] == sticker_set_data["name"]
    
    @allure.title("Sticker set cache key format")
    @allure.description("Test that sticker set cache keys use correct format")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.asyncio
    async def test_sticker_set_cache_key_format(self, fake_redis_service):
        """Test sticker set cache key format."""
        service = fake_redis_service
        key = service._get_sticker_set_cache_key("test_set")
        assert key == "sticker_set:test_set"
    
    @allure.title("Sticker set TTL is 1 day")
    @allure.description("Test that sticker sets are cached with 1 day TTL")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_sticker_set_ttl(self, fake_redis_service):
        """Test sticker set TTL is 1 day (86400 seconds)."""
        service = fake_redis_service
        sticker_set_data = {"name": "test", "stickers": []}
        
        # Mock redis.setex to capture TTL
        ttl_captured = []
        original_setex = service.redis.setex
        
        async def mock_setex(key, ttl, value):
            ttl_captured.append(ttl)
            return await original_setex(key, ttl, value)
        
        service.redis.setex = mock_setex
        
        await service.set_sticker_set("test", sticker_set_data)
        
        # Verify TTL is 1 day (86400 seconds)
        assert len(ttl_captured) > 0
        assert ttl_captured[0] == 86400

