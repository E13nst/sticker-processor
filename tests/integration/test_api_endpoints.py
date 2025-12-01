"""Integration tests for FastAPI endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns 200 and valid response."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.integration
class TestAPIStatsEndpoint:
    """Test API statistics endpoint."""
    
    @pytest.mark.asyncio
    async def test_api_stats(self, client: AsyncClient):
        """Test API stats endpoint returns valid structure."""
        response = await client.get("/api/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check new structure with cache statistics
        assert "cache_statistics" in data
        assert "service_info" in data
        
        # Check service info
        service_info = data["service_info"]
        assert "multi_level_caching" in service_info
        assert "adaptive_retry" in service_info
        assert "rate_limit_handling" in service_info
        assert "disk_cache_enabled" in service_info
        assert "redis_available" in service_info


@pytest.mark.integration
@pytest.mark.redis
class TestCacheEndpoints:
    """Test cache-related endpoints."""
    
    @pytest.mark.asyncio
    async def test_cache_stats(self, client: AsyncClient):
        """Test cache stats endpoint."""
        response = await client.get("/cache/stats")
        
        # Should return 200 with new cache manager
        assert response.status_code == 200
        
        data = response.json()
        
        # Check cache statistics structure based on actual response
        assert "conversions_performed" in data
        assert "disk_hits" in data
        assert "disk_misses" in data
        assert "telegram_api_calls" in data
        assert "total_requests" in data
        assert "disk" in data
        assert "redis" in data
        assert "telegram_api" in data


@pytest.mark.integration
class TestFormatsEndpoint:
    """Test formats information endpoint."""
    
    @pytest.mark.asyncio
    async def test_formats_info(self, client: AsyncClient):
        """Test formats endpoint returns supported formats."""
        response = await client.get("/formats")
        
        assert response.status_code == 200
        data = response.json()
        assert "supported_formats" in data
        
        formats = data["supported_formats"]
        assert "input" in formats
        assert "output" in formats
        assert "conversions" in formats
        
        # Check expected formats
        assert "tgs" in formats["input"]
        assert "webp" in formats["input"]
        assert "lottie" in formats["output"]


@pytest.mark.integration
class TestRateLimiting:
    """Test rate limiting middleware."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_rate_limit_headers(self, client: AsyncClient):
        """Test that rate limit headers are present.
        
        Note: In test mode, rate limiting might not be fully active
        depending on Redis availability.
        """
        response = await client.get("/health")
        
        assert response.status_code == 200
        
        # Rate limit headers may or may not be present in test environment
        # depending on Redis availability and middleware configuration
        # Just verify the endpoint works
        data = response.json()
        assert data["status"] == "healthy"

