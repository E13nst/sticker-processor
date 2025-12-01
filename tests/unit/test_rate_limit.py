"""Unit tests for rate limit middleware."""
import pytest
import allure
from unittest.mock import Mock, AsyncMock
from fastapi import Request
from starlette.responses import Response
from app.middleware.rate_limit import RateLimitMiddleware


@allure.feature("Rate Limiting")
@allure.tag("middleware", "rate-limit", "unit")
@pytest.mark.unit
class TestRateLimitMiddleware:
    """Test RateLimitMiddleware functionality."""
    
    @allure.title("Middleware initialization")
    @allure.description("Test that middleware initializes with correct settings")
    @allure.severity(allure.severity_level.NORMAL)
    def test_middleware_initialization(self, rate_limit_middleware):
        """Test middleware initializes correctly."""
        with allure.step("Check middleware instance"):
            assert rate_limit_middleware is not None
            assert rate_limit_middleware.enabled is True
        
        with allure.step("Verify rate limit settings"):
            assert rate_limit_middleware.max_requests > 0
            assert rate_limit_middleware.window_seconds > 0
    
    @allure.title("Client identification - X-Forwarded-For")
    @allure.description("Test that client is identified from X-Forwarded-For header")
    @allure.severity(allure.severity_level.NORMAL)
    def test_get_client_identifier_forwarded_for(self, rate_limit_middleware):
        """Test client identification from X-Forwarded-For header."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request.client = None
        
        with allure.step("Extract client ID from X-Forwarded-For"):
            client_id = rate_limit_middleware._get_client_identifier(request)
            assert client_id == "192.168.1.1"
    
    @allure.title("Client identification - direct client")
    @allure.description("Test that client is identified from request client")
    @allure.severity(allure.severity_level.NORMAL)
    def test_get_client_identifier_direct(self, rate_limit_middleware):
        """Test client identification from request client."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.100"
        
        with allure.step("Extract client ID from client host"):
            client_id = rate_limit_middleware._get_client_identifier(request)
            assert client_id == "192.168.1.100"
    
    @allure.title("Client identification - unknown")
    @allure.description("Test that unknown client returns 'unknown'")
    @allure.severity(allure.severity_level.MINOR)
    def test_get_client_identifier_unknown(self, rate_limit_middleware):
        """Test client identification when no info available."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = None
        
        with allure.step("Return 'unknown' when no client info"):
            client_id = rate_limit_middleware._get_client_identifier(request)
            assert client_id == "unknown"
    
    @allure.title("Rate limit check - within limit")
    @allure.description("Test that requests within limit are allowed")
    @allure.severity(allure.severity_level.NORMAL)
    def test_is_rate_limited_within_limit(self, rate_limit_middleware):
        """Test rate limit check when within limit."""
        client_id = "test_client"
        
        with allure.step("Check first request"):
            is_limited = rate_limit_middleware._is_rate_limited(client_id)
            assert is_limited is False
        
        with allure.step("Check multiple requests within limit"):
            for _ in range(rate_limit_middleware.max_requests - 1):
                is_limited = rate_limit_middleware._is_rate_limited(client_id)
                assert is_limited is False
    
    @allure.title("Rate limit check - exceeded limit")
    @allure.description("Test that requests exceeding limit are blocked")
    @allure.severity(allure.severity_level.NORMAL)
    def test_is_rate_limited_exceeded(self, rate_limit_middleware):
        """Test rate limit check when limit exceeded."""
        client_id = "test_client_exceeded"
        
        with allure.step("Make requests up to limit"):
            for _ in range(rate_limit_middleware.max_requests):
                rate_limit_middleware._is_rate_limited(client_id)
        
        with allure.step("Next request should be limited"):
            is_limited = rate_limit_middleware._is_rate_limited(client_id)
            assert is_limited is True
    
    @allure.title("Rate limit check - new window")
    @allure.description("Test that rate limit resets in new time window")
    @allure.severity(allure.severity_level.NORMAL)
    def test_is_rate_limited_new_window(self, rate_limit_middleware, monkeypatch):
        """Test rate limit resets in new window."""
        client_id = "test_client_window"
        
        with allure.step("Exceed limit in current window"):
            for _ in range(rate_limit_middleware.max_requests + 1):
                rate_limit_middleware._is_rate_limited(client_id)
        
        with allure.step("Simulate new time window"):
            import time
            future_time = time.time() + rate_limit_middleware.window_seconds + 1
            monkeypatch.setattr(time, 'time', lambda: future_time)
        
        with allure.step("Request in new window should be allowed"):
            is_limited = rate_limit_middleware._is_rate_limited(client_id)
            assert is_limited is False
    
    @allure.title("Cleanup old entries")
    @allure.description("Test cleanup of old rate limit entries")
    @allure.severity(allure.severity_level.MINOR)
    def test_cleanup_old_entries(self, rate_limit_middleware, monkeypatch):
        """Test cleanup of old entries."""
        client_id = "test_client_cleanup"
        
        with allure.step("Add entry for client"):
            rate_limit_middleware._is_rate_limited(client_id)
            assert client_id in rate_limit_middleware.requests
        
        with allure.step("Simulate old entry"):
            import time
            old_time = time.time() - (rate_limit_middleware.window_seconds * 3)
            rate_limit_middleware.requests[client_id] = (1, old_time)
        
        with allure.step("Run cleanup"):
            rate_limit_middleware._cleanup_old_entries()
        
        with allure.step("Verify entry is cleaned up"):
            assert client_id not in rate_limit_middleware.requests
    
    @allure.title("Skip rate limit for health endpoint")
    @allure.description("Test that /health endpoint is not rate limited")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_skip_health_endpoint(self, rate_limit_middleware):
        """Test that health endpoint is not rate limited."""
        request = Mock(spec=Request)
        request.url.path = "/health"
        request.headers = {}
        request.client = Mock()
        request.client.host = "test_client"
        
        call_next = AsyncMock(return_value=Response())
        
        with allure.step("Dispatch health check request"):
            response = await rate_limit_middleware.dispatch(request, call_next)
            assert response.status_code == 200
        
        with allure.step("Verify call_next was called"):
            call_next.assert_called_once()
    
    @allure.title("Rate limit response headers")
    @allure.description("Test that rate limit headers are added to response")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, rate_limit_middleware):
        """Test rate limit headers in response."""
        request = Mock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {}
        request.client = Mock()
        request.client.host = "test_client"
        
        response = Response()
        call_next = AsyncMock(return_value=response)
        
        with allure.step("Dispatch request"):
            result = await rate_limit_middleware.dispatch(request, call_next)
        
        with allure.step("Verify rate limit headers"):
            assert "X-RateLimit-Limit" in result.headers
            assert "X-RateLimit-Remaining" in result.headers
            assert "X-RateLimit-Window" in result.headers

