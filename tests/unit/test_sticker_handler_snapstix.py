"""Unit tests for sticker handler snapstix generation functionality."""
import pytest
import allure
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import HTTPException
import aiohttp

from app.handlers.sticker_handler import StickerHandler
from app.services.cache_manager import CacheManager
from app.models.requests import SnapstixGenerateRequest


@allure.feature("Sticker Handler")
@allure.tag("sticker-handler", "snapstix", "unit")
@pytest.mark.unit
class TestStickerHandlerSnapstix:
    """Test StickerHandler generate_snapstix_sticker functionality."""
    
    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        manager = Mock(spec=CacheManager)
        return manager
    
    @pytest.fixture
    def handler(self, mock_cache_manager):
        """Create sticker handler with mock cache manager."""
        return StickerHandler(mock_cache_manager)
    
    @pytest.fixture
    def sample_request(self):
        """Sample SnapstixGenerateRequest."""
        return SnapstixGenerateRequest(
            prompt="cute cat with sunglasses",
            callback_url="https://example.com/callback",
            processing_id="test-processing-id-123"
        )
    
    @pytest.fixture
    def sample_runpod_response(self):
        """Sample RunPod API response."""
        return {
            "id": "test-job-id",
            "status": "IN_QUEUE"
        }
    
    @allure.title("Generate Snapstix sticker successfully")
    @allure.description("Test successful sticker generation via Snapstix/RunPod")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_success(
        self, handler, sample_request, sample_runpod_response
    ):
        """Test successful Snapstix sticker generation."""
        # Mock RunPodService
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(return_value=sample_runpod_response)
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        result = await handler.generate_snapstix_sticker(sample_request)
        
        # Verify response
        assert result is not None
        assert result.status_code == 200
        
        # Verify RunPod service was called correctly
        mock_runpod_service.generate_sticker.assert_called_once_with(
            prompt=sample_request.prompt,
            callback_url=sample_request.callback_url,
            processing_id=sample_request.processing_id
        )
    
    @allure.title("Generate Snapstix sticker with auto-generated processing_id")
    @allure.description("Test sticker generation when processing_id is not provided")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_auto_id(
        self, handler, sample_runpod_response
    ):
        """Test Snapstix sticker generation with auto-generated processing_id."""
        request = SnapstixGenerateRequest(
            prompt="happy robot",
            callback_url="https://example.com/callback"
            # processing_id not provided
        )
        
        # Mock RunPodService
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(return_value=sample_runpod_response)
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        result = await handler.generate_snapstix_sticker(request)
        
        # Verify response
        assert result is not None
        assert result.status_code == 200
        
        # Verify RunPod service was called (processing_id should be generated)
        mock_runpod_service.generate_sticker.assert_called_once()
        call_args = mock_runpod_service.generate_sticker.call_args
        assert call_args.kwargs['prompt'] == request.prompt
        assert call_args.kwargs['callback_url'] == request.callback_url
        # processing_id should be provided (either None or a UUID string)
        assert 'processing_id' in call_args.kwargs
    
    @allure.title("Generate Snapstix sticker - template loading error")
    @allure.description("Test error handling when template file cannot be loaded")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_template_error(
        self, handler, sample_request
    ):
        """Test error handling when template loading fails."""
        # Mock RunPodService to raise ValueError (template loading error)
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(
            side_effect=ValueError("Template file not found")
        )
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        with pytest.raises(HTTPException) as exc_info:
            await handler.generate_snapstix_sticker(sample_request)
            
        assert exc_info.value.status_code == 400
        assert "Failed to generate sticker" in str(exc_info.value.detail)
    
    @allure.title("Generate Snapstix sticker - RunPod API server error")
    @allure.description("Test error handling when RunPod API returns server error")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_runpod_server_error(
        self, handler, sample_request
    ):
        """Test error handling when RunPod API returns server error."""
        # Mock RunPodService to raise ClientResponseError with 500 status
        mock_response_error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
            message="Internal Server Error"
        )
        
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(side_effect=mock_response_error)
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        with pytest.raises(HTTPException) as exc_info:
            await handler.generate_snapstix_sticker(sample_request)
        
        assert exc_info.value.status_code == 502
        assert "RunPod API server error" in str(exc_info.value.detail)
    
    @allure.title("Generate Snapstix sticker - RunPod API timeout")
    @allure.description("Test error handling when RunPod API request times out")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_timeout(
        self, handler, sample_request
    ):
        """Test error handling when RunPod API request times out."""
        # Mock RunPodService to raise TimeoutError
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        with pytest.raises(HTTPException) as exc_info:
            await handler.generate_snapstix_sticker(sample_request)
            
        assert exc_info.value.status_code == 504
        assert "timed out" in str(exc_info.value.detail).lower()
    
    @allure.title("Generate Snapstix sticker - RunPod API rate limit")
    @allure.description("Test error handling when RunPod API returns rate limit error")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_rate_limit(
        self, handler, sample_request
    ):
        """Test error handling when RunPod API returns rate limit error."""
        # Mock RunPodService to raise ClientResponseError with 429 status
        mock_response_error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
            message="Too Many Requests"
        )
        
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(side_effect=mock_response_error)
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        with pytest.raises(HTTPException) as exc_info:
            await handler.generate_snapstix_sticker(sample_request)
        
        assert exc_info.value.status_code == 503
        assert "rate limited" in str(exc_info.value.detail).lower()
    
    @allure.title("Generate Snapstix sticker - generic error")
    @allure.description("Test error handling for unexpected errors")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_snapstix_sticker_generic_error(
        self, handler, sample_request
    ):
        """Test error handling for unexpected errors."""
        # Mock RunPodService to raise generic exception
        mock_runpod_service = AsyncMock()
        mock_runpod_service.generate_sticker = AsyncMock(
            side_effect=Exception("Unexpected error")
        )
        
        # Patch the _runpod_service attribute directly
        handler._runpod_service = mock_runpod_service
        with pytest.raises(HTTPException) as exc_info:
            await handler.generate_snapstix_sticker(sample_request)
            
        assert exc_info.value.status_code == 500
        assert "Internal server error" in str(exc_info.value.detail)

