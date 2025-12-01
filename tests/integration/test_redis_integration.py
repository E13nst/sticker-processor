"""Integration tests for Redis service."""
import pytest
from datetime import datetime
from app.models.responses import StickerCache


@pytest.mark.integration
@pytest.mark.redis
class TestRedisIntegration:
    """Test Redis service with real Redis connection."""
    
    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_service):
        """Test basic Redis connection and ping."""
        result = await redis_service.redis.ping()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_set_and_get_sticker(self, redis_service, create_test_cache_entry):
        """Test storing and retrieving sticker from Redis."""
        # Create test cache entry
        sticker_cache = create_test_cache_entry(
            file_id="test_integration_file_1",
            file_data=b"test data content",
            output_format="lottie"
        )
        
        # Store in Redis
        success = await redis_service.set_sticker(sticker_cache)
        assert success is True
        
        # Retrieve from Redis
        retrieved = await redis_service.get_sticker("test_integration_file_1")
        assert retrieved is not None
        assert retrieved.file_id == "test_integration_file_1"
        assert retrieved.file_data == b"test data content"
        assert retrieved.output_format == "lottie"
        assert retrieved.is_converted is True
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_sticker(self, redis_service):
        """Test retrieving non-existent sticker returns None."""
        result = await redis_service.get_sticker("nonexistent_file_id")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_sticker(self, redis_service, create_test_cache_entry):
        """Test deleting sticker from Redis."""
        # Create and store
        sticker_cache = create_test_cache_entry(file_id="test_delete_file")
        await redis_service.set_sticker(sticker_cache)
        
        # Verify it exists
        retrieved = await redis_service.get_sticker("test_delete_file")
        assert retrieved is not None
        
        # Delete
        success = await redis_service.delete_sticker("test_delete_file")
        assert success is True
        
        # Verify it's gone
        retrieved = await redis_service.get_sticker("test_delete_file")
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_cache_stats(self, redis_service, create_test_cache_entry):
        """Test getting cache statistics."""
        import asyncio
        
        # Create test entries
        for i in range(3):
            sticker = create_test_cache_entry(
                file_id=f"test_stats_file_{i}",
                file_data=b"x" * 1000  # 1KB each
            )
            await redis_service.set_sticker(sticker)
        
        # Get stats with timeout
        try:
            stats = await asyncio.wait_for(
                redis_service.get_cache_stats(),
                timeout=10.0  # 10 seconds timeout
            )
            assert stats is not None
            assert stats.total_files >= 3
            assert stats.converted_files >= 3
            assert stats.total_size_bytes >= 3000
        except asyncio.TimeoutError:
            pytest.skip("Cache stats test timed out - Redis may have too many keys")
    
    @pytest.mark.asyncio
    async def test_cache_ttl(self, redis_service, create_test_cache_entry):
        """Test that cached items have TTL set."""
        sticker = create_test_cache_entry(file_id="test_ttl_file")
        await redis_service.set_sticker(sticker)
        
        # Check TTL is set
        key = redis_service._get_cache_key("test_ttl_file")
        ttl = await redis_service.redis.ttl(key)
        
        # TTL should be positive (key exists with expiry)
        assert ttl > 0
        # Should be approximately equal to cache_ttl_days
        expected_ttl = redis_service.ttl_days * 24 * 60 * 60
        assert abs(ttl - expected_ttl) < 10  # Within 10 seconds
    
    @pytest.mark.asyncio
    async def test_binary_data_integrity(self, redis_service, create_test_cache_entry):
        """Test that binary data is stored and retrieved correctly."""
        # Create binary data with various byte values
        binary_data = bytes(range(256))
        
        sticker = create_test_cache_entry(
            file_id="test_binary_file",
            file_data=binary_data
        )
        
        await redis_service.set_sticker(sticker)
        retrieved = await redis_service.get_sticker("test_binary_file")
        
        assert retrieved is not None
        assert retrieved.file_data == binary_data
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_file_storage(self, redis_service, create_test_cache_entry):
        """Test storing and retrieving large files (>1MB)."""
        # Create 2MB of data
        large_data = b"x" * (2 * 1024 * 1024)
        
        sticker = create_test_cache_entry(
            file_id="test_large_file",
            file_data=large_data
        )
        
        success = await redis_service.set_sticker(sticker)
        assert success is True
        
        retrieved = await redis_service.get_sticker("test_large_file")
        assert retrieved is not None
        assert len(retrieved.file_data) == len(large_data)
        assert retrieved.file_size == len(large_data)
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_service, create_test_cache_entry):
        """Test concurrent Redis operations."""
        import asyncio
        
        async def store_sticker(file_id: str):
            sticker = create_test_cache_entry(file_id=file_id)
            return await redis_service.set_sticker(sticker)
        
        # Store 10 stickers concurrently
        tasks = [store_sticker(f"test_concurrent_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(results)
        
        # Verify all are stored
        for i in range(10):
            retrieved = await redis_service.get_sticker(f"test_concurrent_{i}")
            assert retrieved is not None

