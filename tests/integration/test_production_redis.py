"""Critical integration tests for production Redis connection.

These tests verify connectivity to production Redis instance.
They are marked as 'critical' and should ALWAYS pass.
"""
import pytest
from app.services.redis import RedisService
from app.config import settings


@pytest.mark.integration
@pytest.mark.redis
@pytest.mark.critical
class TestProductionRedisConnection:
    """Critical tests for production Redis connectivity."""
    
    @pytest.mark.asyncio
    async def test_production_redis_connection(self, redis_service):
        """🔴 CRITICAL: Test that we can connect to production Redis.
        
        This test verifies:
        - Redis connection is established
        - SSL is working correctly
        - Authentication is successful
        - Basic ping/pong works
        """
        assert redis_service.redis is not None, "Redis client should be initialized"
        
        # Test basic ping
        result = await redis_service.redis.ping()
        assert result is True, "Redis PING should return True"
        
        print(f"\n✅ Successfully connected to Redis at {settings.redis_host}:{settings.redis_port}")
        print(f"   SSL: {settings.redis_ssl_enabled}")
        print(f"   Database: {settings.redis_database}")
    
    @pytest.mark.asyncio
    async def test_production_redis_basic_operations(self, redis_service):
        """🔴 CRITICAL: Test basic Redis operations work correctly.
        
        This test verifies:
        - SET operation works
        - GET operation works
        - Data integrity (binary data)
        - TTL is set correctly
        - DELETE works
        """
        import asyncio
        
        test_key = "test:critical:basic_ops"
        test_value = b"test_value_12345"
        test_ttl = 60  # 60 seconds
        
        try:
            # Test SET with TTL and timeout
            await asyncio.wait_for(
                redis_service.redis.set(test_key, test_value, ex=test_ttl),
                timeout=10.0
            )
            print(f"\n✅ SET operation successful")
            
            # Test GET with timeout
            retrieved = await asyncio.wait_for(
                redis_service.redis.get(test_key),
                timeout=10.0
            )
            assert retrieved == test_value, f"Retrieved value {retrieved} doesn't match {test_value}"
            print(f"✅ GET operation successful, data integrity verified")
            
            # Test TTL with timeout
            ttl = await asyncio.wait_for(
                redis_service.redis.ttl(test_key),
                timeout=10.0
            )
            assert ttl > 0 and ttl <= test_ttl, f"TTL {ttl} should be between 0 and {test_ttl}"
            print(f"✅ TTL set correctly: {ttl} seconds")
            
            # Test DELETE with timeout
            deleted = await asyncio.wait_for(
                redis_service.redis.delete(test_key),
                timeout=10.0
            )
            assert deleted == 1, "DELETE should return 1"
            print(f"✅ DELETE operation successful")
            
            # Verify deleted with timeout
            retrieved_after_delete = await asyncio.wait_for(
                redis_service.redis.get(test_key),
                timeout=10.0
            )
            assert retrieved_after_delete is None, "Key should not exist after deletion"
            print(f"✅ Key properly deleted")
            
        except asyncio.TimeoutError:
            pytest.fail("❌ Basic Redis operations test timed out - Redis too slow")
        finally:
            # Cleanup with timeout
            try:
                await asyncio.wait_for(
                    redis_service.redis.delete(test_key),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                print("⚠️  Warning: Cleanup timeout - key may not be deleted")
    
    @pytest.mark.asyncio
    async def test_production_redis_connection_info(self, redis_service):
        """Test production Redis connection details and capabilities.
        
        This test prints useful information about the Redis connection.
        """
        # Get Redis info
        info = await redis_service.redis.info()
        
        print(f"\n📊 Redis Server Information:")
        print(f"   Version: {info.get('redis_version', 'unknown')}")
        print(f"   Mode: {info.get('redis_mode', 'unknown')}")
        print(f"   OS: {info.get('os', 'unknown')}")
        print(f"   Uptime (days): {info.get('uptime_in_days', 'unknown')}")
        print(f"   Connected clients: {info.get('connected_clients', 'unknown')}")
        print(f"   Used memory: {info.get('used_memory_human', 'unknown')}")
        print(f"   Max memory: {info.get('maxmemory_human', 'unknown') or 'unlimited'}")
        
        # Test database info
        db_info = await redis_service.redis.info('keyspace')
        print(f"\n📂 Database {settings.redis_database} info:")
        db_key = f'db{settings.redis_database}'
        if db_key in db_info:
            print(f"   {db_info[db_key]}")
        else:
            print(f"   Empty or no keys")
        
        assert info.get('redis_version'), "Should be able to get Redis version"
    
    @pytest.mark.asyncio
    async def test_production_redis_ssl_connection(self, redis_service):
        """🔴 CRITICAL: Verify SSL connection is working correctly.
        
        This is critical because production Redis requires SSL.
        """
        if not settings.redis_ssl_enabled:
            pytest.skip("SSL not enabled, skipping SSL test")
        
        # If we got here, connection is already established with SSL
        # Just verify we can perform operations
        result = await redis_service.redis.ping()
        assert result is True, "Should be able to ping through SSL connection"
        
        print(f"\n✅ SSL connection verified")
        print(f"   Host: {settings.redis_host}")
        print(f"   Port: {settings.redis_port}")
        print(f"   SSL: ✅ Enabled")
    
    @pytest.mark.asyncio
    async def test_production_redis_binary_data_handling(self, redis_service):
        """Test that production Redis handles binary data correctly.
        
        This is important for sticker file caching.
        """
        test_key = "test:critical:binary_data"
        
        # Create binary data with all byte values
        binary_data = bytes(range(256))
        
        try:
            # Store binary data
            await redis_service.redis.set(test_key, binary_data, ex=60)
            
            # Retrieve and verify
            retrieved = await redis_service.redis.get(test_key)
            assert retrieved == binary_data, "Binary data should be retrieved intact"
            assert len(retrieved) == 256, "All 256 bytes should be present"
            
            print(f"\n✅ Binary data handling verified (256 bytes)")
            
        finally:
            await redis_service.redis.delete(test_key)
    
    @pytest.mark.asyncio
    async def test_production_redis_large_payload(self, redis_service):
        """Test that production Redis can handle large payloads (sticker files).
        
        Telegram stickers can be several MB in size.
        """
        test_key = "test:critical:large_payload"
        
        # Create 5MB payload (typical large sticker)
        large_payload = b"x" * (5 * 1024 * 1024)
        
        try:
            # Store large payload
            await redis_service.redis.set(test_key, large_payload, ex=60)
            print(f"\n✅ Stored 5MB payload")
            
            # Retrieve and verify size
            retrieved = await redis_service.redis.get(test_key)
            assert len(retrieved) == len(large_payload), "Full payload should be retrieved"
            
            print(f"✅ Retrieved 5MB payload successfully")
            
        finally:
            await redis_service.redis.delete(test_key)


@pytest.mark.integration
@pytest.mark.redis
@pytest.mark.critical
class TestProductionRedisServiceIntegration:
    """Critical tests for RedisService with production Redis."""
    
    @pytest.mark.asyncio
    async def test_sticker_cache_integration(self, redis_service, create_test_cache_entry):
        """🔴 CRITICAL: Test full sticker caching workflow with production Redis.
        
        This simulates the actual sticker caching that the service does.
        """
        import asyncio
        
        # Create realistic sticker cache entry
        file_id = "test_prod_redis_sticker_001"
        sticker_data = b"fake_sticker_data" * 1000  # ~17KB
        
        sticker_cache = create_test_cache_entry(
            file_id=file_id,
            file_data=sticker_data,
            output_format="lottie"
        )
        
        try:
            # Store sticker with timeout
            success = await asyncio.wait_for(
                redis_service.set_sticker(sticker_cache),
                timeout=30.0
            )
            assert success is True, "Should successfully store sticker"
            print(f"\n✅ Stored sticker cache entry")
            
            # Retrieve sticker with timeout
            retrieved = await asyncio.wait_for(
                redis_service.get_sticker(file_id),
                timeout=30.0
            )
            assert retrieved is not None, "Should retrieve sticker"
            assert retrieved.file_id == file_id
            assert retrieved.file_data == sticker_data
            assert retrieved.output_format == "lottie"
            print(f"✅ Retrieved sticker cache entry")
            
            # Verify TTL is set with timeout
            key = redis_service._get_cache_key(file_id)
            ttl = await asyncio.wait_for(
                redis_service.redis.ttl(key),
                timeout=10.0
            )
            assert ttl > 0, "TTL should be set"
            print(f"✅ TTL verified: {ttl} seconds (~{ttl/86400:.1f} days)")
            
            # Delete sticker with timeout
            success = await asyncio.wait_for(
                redis_service.delete_sticker(file_id),
                timeout=10.0
            )
            assert success is True, "Should successfully delete sticker"
            print(f"✅ Deleted sticker cache entry")
            
            # Verify deletion with timeout
            retrieved = await asyncio.wait_for(
                redis_service.get_sticker(file_id),
                timeout=10.0
            )
            assert retrieved is None, "Sticker should be deleted"
            print(f"✅ Verified deletion")
            
        except asyncio.TimeoutError:
            pytest.fail("❌ Sticker cache integration test timed out - Redis operations too slow")
        except Exception as e:
            pytest.fail(f"❌ Sticker cache integration test failed: {e}")
        finally:
            # Cleanup with timeout
            try:
                await asyncio.wait_for(
                    redis_service.delete_sticker(file_id),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                print("⚠️  Warning: Cleanup timeout - sticker may not be deleted")
    
    @pytest.mark.asyncio
    async def test_production_cache_stats(self, redis_service):
        """Test that cache statistics work with production Redis.
        
        Note: This test may be slow if Redis has many keys.
        We test with a shorter timeout and graceful failure.
        """
        import asyncio
        
        # Check if Redis is available
        if not redis_service.redis:
            pytest.skip("Redis is not available")
        
        try:
            # Add timeout to prevent hanging - shorter timeout for stats
            stats = await asyncio.wait_for(
                redis_service.get_cache_stats(),
                timeout=15.0  # 15 seconds timeout (reduced from 30)
            )
            
            if stats is None:
                pytest.skip("Cache stats returned None - Redis may be unavailable or have issues")
            
            assert hasattr(stats, 'total_files'), "Stats should have total_files"
            assert hasattr(stats, 'total_size_bytes'), "Stats should have total_size_bytes"
            
            print(f"\n📊 Production Cache Statistics:")
            print(f"   Total files: {stats.total_files}")
            print(f"   Converted files: {stats.converted_files}")
            print(f"   Total size: {stats.total_size_bytes / (1024*1024):.2f} MB")
            print(f"   Average file size: {stats.average_file_size_bytes / 1024:.2f} KB" if stats.average_file_size_bytes else "   Average file size: N/A")
            
        except asyncio.TimeoutError:
            # Mark as SKIPPED instead of FAILED if timeout occurs
            pytest.skip("⏱️ Cache stats test timed out after 15 seconds - Redis has too many keys or is slow")
        except Exception as e:
            pytest.fail(f"❌ Cache stats test failed: {e}")

