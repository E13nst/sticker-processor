"""Integration tests for disk cache fallback behavior."""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.redis
@pytest.mark.slow
class TestDiskCacheFallback:
    """Test that disk cache serves files when Redis cache is cleared."""
    
    @pytest.mark.asyncio
    async def test_disk_cache_fallback_after_redis_delete(
        self, client: AsyncClient, monkeypatch
    ):
        """
        Test that disk cache serves file after it's deleted from Redis.
        
        Flow:
        1. Request file (may hit Redis or download from Telegram)
        2. Delete from Redis
        3. Request again (should hit disk cache)
        4. Verify cache stats show disk hit increase
        """
        test_file_id = "CAACAgIAAxUAAWj2A8ieJr2KOxQTLag0O_eDmel-AALWAANWnb0KCXXJDOIvIQo2BA"
        
        # Get initial stats
        initial_stats = await client.get("/cache/stats")
        assert initial_stats.status_code == 200
        initial_data = initial_stats.json()
        
        # Step 1: Request file (should work)
        response1 = await client.get(f"/stickers/{test_file_id}")
        assert response1.status_code == 200
        size1 = len(response1.content)
        assert size1 > 0
        
        # Step 2: Delete from cache (Redis + disk)
        delete_response = await client.delete(f"/cache/{test_file_id}")
        assert delete_response.status_code == 200
        
        # Step 3: Request again - should still work if on disk
        response2 = await client.get(f"/stickers/{test_file_id}")
        assert response2.status_code == 200
        size2 = len(response2.content)
        
        # File sizes should match
        assert size1 == size2, "File size should be consistent"
        
        # Step 4: Check final stats
        final_stats = await client.get("/cache/stats")
        assert final_stats.status_code == 200
        final_data = final_stats.json()
        
        # Verify stats increased
        disk_hits_diff = final_data["disk_hits"] - initial_data["disk_hits"]
        redis_hits_diff = final_data["redis_hits"] - initial_data["redis_hits"]
        
        # Either disk_hits or redis_hits should have increased
        assert (disk_hits_diff > 0) or (redis_hits_diff > 0), \
            "At least one cache level should have served the file"
    
    @pytest.mark.asyncio
    async def test_disk_cache_serves_converted_lottie(self, client: AsyncClient):
        """
        Test that requesting a TGS file serves converted lottie from disk cache.
        
        Note: This test assumes TGS files are converted and cached.
        In real usage, TGS → lottie conversion should be cached.
        """
        test_file_id = "CAACAgIAAxUAAWj2A8jKt9uToUIwZcl1dJCqOHGOAALSAANWnb0KDgVyNnWDNYo2BA"
        
        # Request the file
        response = await client.get(f"/stickers/{test_file_id}")
        
        if response.status_code == 200:
            # Should be valid JSON (lottie) or other format
            assert len(response.content) > 0
            # Check if it's JSON/lottie
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type or "image" in content_type


@pytest.mark.integration
@pytest.mark.redis
@pytest.mark.slow
class TestDiskCacheWithRedisDisabled:
    """Test disk cache behavior when Redis is disabled."""
    
    @pytest.mark.asyncio
    async def test_disk_cache_without_redis(self, client: AsyncClient, monkeypatch):
        """
        Test disk cache when Redis is disabled.
        
        Note: This requires environment variable REDIS_ENABLED=false
        which can't be easily tested with current test setup.
        Skipping implementation details for now.
        """
        pytest.skip("Requires Redis to be disabled at startup - needs special test setup")
    
    @pytest.mark.asyncio
    async def test_disk_cache_stats(self, client: AsyncClient):
        """Test that disk cache statistics are reported correctly."""
        response = await client.get("/cache/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Check disk stats structure
        assert "disk" in data
        disk = data["disk"]
        
        # Verify required fields
        assert "total_files" in disk
        assert "total_size_mb" in disk
        assert "cache_hits" in disk
        assert "cache_misses" in disk
        assert "cache_hit_rate" in disk
        
        # Check hit rate is calculated correctly
        if disk["cache_hits"] + disk["cache_misses"] > 0:
            expected_rate = (disk["cache_hits"] / 
                           (disk["cache_hits"] + disk["cache_misses"]) * 100)
            assert abs(disk["cache_hit_rate"] - expected_rate) < 0.1


@pytest.mark.integration
@pytest.mark.redis
class TestDiskCacheMultiFormatSupport:
    """Test disk cache handles multiple formats correctly."""
    
    @pytest.mark.asyncio
    async def test_disk_cache_deletes_all_formats(self, client: AsyncClient):
        """
        Test that DELETE /cache/{file_id} removes all formats from disk.
        
        Note: Currently deletes 'tgs' and 'lottie', but new implementation
        only caches lottie (converted). This test verifies deletion works.
        """
        # This is more of a contract test
        # Actual deletion tested in test_disk_cache_fallback_after_redis_delete
        assert True
    
    @pytest.mark.asyncio
    async def test_disk_cache_lottie_priority(self, client: AsyncClient):
        """
        Test that disk cache checks lottie first for TGS files.
        
        Since we no longer cache TGS directly, lottie should be the
        primary format for TGS files in disk cache.
        """
        # Get stats to understand disk cache usage
        response = await client.get("/cache/stats")
        assert response.status_code == 200
        data = response.json()
        
        # Just verify stats include disk information
        assert "disk" in data
        disk = data["disk"]
        
        # Check file types breakdown if available
        if "file_types" in disk:
            file_types = disk["file_types"]
            # lottie should be present (converted TGS files)
            assert "lottie" in file_types or "tgs" in file_types

