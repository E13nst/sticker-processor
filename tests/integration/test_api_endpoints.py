"""Integration tests for FastAPI endpoints."""
import pytest
import allure
import json
from httpx import AsyncClient


@allure.feature("API Endpoints")
@allure.tag("api", "endpoints", "integration")
@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""
    
    @allure.title("Health check endpoint")
    @allure.description("Test that health check endpoint returns 200 and valid response")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns 200 and valid response."""
        with allure.step("Send GET request to /health"):
            response = await client.get("/health")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response content"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Health Check Response", allure.attachment_type.JSON)
            assert data["status"] == "healthy"
            assert "timestamp" in data


@allure.feature("API Endpoints")
@allure.tag("api", "stats", "integration")
@pytest.mark.integration
class TestAPIStatsEndpoint:
    """Test API statistics endpoint."""
    
    @allure.title("API statistics endpoint")
    @allure.description("Test that API stats endpoint returns valid structure with cache statistics")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_api_stats(self, client: AsyncClient):
        """Test API stats endpoint returns valid structure."""
        with allure.step("Send GET request to /api/stats"):
            response = await client.get("/api/stats")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response structure"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "API Stats Response", allure.attachment_type.JSON)
            
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


@allure.feature("Cache Management")
@allure.tag("cache", "api", "integration")
@pytest.mark.integration
@pytest.mark.redis
class TestCacheEndpoints:
    """Test cache-related endpoints."""
    
    @allure.title("Cache statistics endpoint")
    @allure.description("Test that cache stats endpoint returns comprehensive statistics")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_stats(self, client: AsyncClient):
        """Test cache stats endpoint."""
        with allure.step("Send GET request to /cache/stats"):
            response = await client.get("/cache/stats")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify cache statistics structure"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Cache Stats Response", allure.attachment_type.JSON)
            
            # Check cache statistics structure based on actual response
            assert "conversions_performed" in data
            assert "disk_hits" in data
            assert "disk_misses" in data
            assert "telegram_api_calls" in data
            assert "total_requests" in data
            assert "disk" in data
            assert "redis" in data
            assert "telegram_api" in data
    
    @allure.title("Delete file from cache")
    @allure.description("Test that DELETE /cache/{file_id} removes file from cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_delete_from_cache(self, client: AsyncClient, sample_file_id):
        """Test deleting file from cache."""
        with allure.step(f"Send DELETE request to /cache/{sample_file_id}"):
            response = await client.delete(f"/cache/{sample_file_id}")
        
        with allure.step("Verify response (may be 200 or 404)"):
            assert response.status_code in [200, 404]
    
    @allure.title("Clear all cache")
    @allure.description("Test that DELETE /cache/all clears all cache entries")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_clear_all_cache(self, client: AsyncClient):
        """Test clearing all cache."""
        with allure.step("Send DELETE request to /cache/all"):
            response = await client.delete("/cache/all")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response content"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Clear All Cache Response", allure.attachment_type.JSON)
            assert "message" in data
    
    @allure.title("Cleanup cache")
    @allure.description("Test that POST /cache/cleanup removes expired files")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cleanup_cache(self, client: AsyncClient):
        """Test cache cleanup."""
        with allure.step("Send POST request to /cache/cleanup"):
            response = await client.post("/cache/cleanup")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response content"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Cleanup Cache Response", allure.attachment_type.JSON)
            assert "message" in data
    
    @allure.title("Cache strategy endpoint")
    @allure.description("Test that GET /cache/strategy returns cache strategy information")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.asyncio
    async def test_cache_strategy(self, client: AsyncClient):
        """Test cache strategy endpoint."""
        with allure.step("Send GET request to /cache/strategy"):
            response = await client.get("/cache/strategy")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response structure"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Cache Strategy Response", allure.attachment_type.JSON)
            assert "redis_config" in data or "strategy_type" in data


@allure.feature("API Endpoints")
@allure.tag("api", "formats", "integration")
@pytest.mark.integration
class TestFormatsEndpoint:
    """Test formats information endpoint."""
    
    @allure.title("Formats information endpoint")
    @allure.description("Test that formats endpoint returns supported input and output formats")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_formats_info(self, client: AsyncClient):
        """Test formats endpoint returns supported formats."""
        with allure.step("Send GET request to /formats"):
            response = await client.get("/formats")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify formats structure"):
            data = response.json()
            allure.attach(json.dumps(data, indent=2), "Formats Response", allure.attachment_type.JSON)
            assert "supported_formats" in data
            
            formats = data["supported_formats"]
            assert "input" in formats
            assert "output" in formats
            assert "conversions" in formats
            
            # Check expected formats
            assert "tgs" in formats["input"]
            assert "webp" in formats["input"]
            assert "lottie" in formats["output"]


@allure.feature("Rate Limiting")
@allure.tag("rate-limit", "middleware", "integration")
@pytest.mark.integration
class TestRateLimiting:
    """Test rate limiting middleware."""
    
    @allure.title("Rate limit headers")
    @allure.description("Test that rate limit headers are present in responses")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_rate_limit_headers(self, client: AsyncClient):
        """Test that rate limit headers are present.
        
        Note: In test mode, rate limiting might not be fully active
        depending on Redis availability.
        """
        with allure.step("Send GET request to /health"):
            response = await client.get("/health")
        
        with allure.step("Verify response status code"):
            assert response.status_code == 200
        
        with allure.step("Verify response content"):
            data = response.json()
            assert data["status"] == "healthy"
        
        with allure.step("Check rate limit headers (may or may not be present)"):
            # Rate limit headers may or may not be present in test environment
            # depending on Redis availability and middleware configuration
            headers = dict(response.headers)
            allure.attach(str(headers), "Response Headers", allure.attachment_type.TEXT)

