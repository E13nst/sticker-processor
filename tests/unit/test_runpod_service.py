"""Unit tests for RunPod service."""
import pytest
import allure
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock, mock_open
import aiohttp

from app.services.runpod_service import RunPodService, TEMPLATE_PATH


@allure.feature("RunPod Service")
@allure.tag("runpod", "service", "unit")
@pytest.mark.unit
class TestRunPodService:
    """Test RunPodService functionality."""
    
    @pytest.fixture
    def service(self):
        """Create RunPodService instance."""
        service = RunPodService()
        # Clear template cache to ensure fresh state
        service.template_cache = None
        return service
    
    @pytest.fixture
    def sample_template(self):
        """Sample template structure."""
        return {
            "input": {
                "style_id": "8b93c386-8fa3-4833-928e-065be29fd16b",
                "callback_url": "{{callback_url}}",
                "prompt": "{{prompt}}",
                "processing_job_id": "{{processing_id}}",
                "workflow": {
                    "17": {
                        "inputs": {
                            "positive": "realistic sticker {{prompt}}, plain background"
                        }
                    }
                }
            }
        }
    
    @allure.title("Load template successfully")
    @allure.description("Test loading template from example.json file")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_load_template_success(self, service, sample_template):
        """Test successful template loading."""
        # Mock file reading
        with patch('builtins.open', mock_open(read_data=json.dumps(sample_template))):
            with patch.object(Path, 'exists', return_value=True):
                template = service._load_template()
                
                assert template is not None
                assert template == sample_template
                # Template should be cached
                assert service.template_cache == sample_template
    
    @allure.title("Load template - file not found")
    @allure.description("Test error handling when template file doesn't exist")
    @allure.severity(allure.severity_level.NORMAL)
    def test_load_template_file_not_found(self, service):
        """Test error handling when template file doesn't exist."""
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(FileNotFoundError) as exc_info:
                service._load_template()
            
            assert "Template file not found" in str(exc_info.value)
    
    @allure.title("Substitute template placeholders")
    @allure.description("Test substituting placeholders in template")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_substitute_template(self, service, sample_template):
        """Test template placeholder substitution."""
        prompt = "cute cat"
        processing_id = "test-id-123"
        callback_url = "https://example.com/callback"
        
        result = service._substitute_template(
            sample_template, prompt, processing_id, callback_url
        )
        
        # Verify substitutions
        assert result["input"]["prompt"] == prompt
        assert result["input"]["processing_job_id"] == processing_id
        assert result["input"]["callback_url"] == callback_url
        assert result["input"]["workflow"]["17"]["inputs"]["positive"] == f"realistic sticker {prompt}, plain background"
        
        # Verify original template is not modified
        assert sample_template["input"]["prompt"] == "{{prompt}}"
    
    @allure.title("Generate sticker successfully")
    @allure.description("Test successful sticker generation request to RunPod API")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_generate_sticker_success(self, service, sample_template):
        """Test successful sticker generation."""
        prompt = "cute cat"
        callback_url = "https://example.com/callback"
        processing_id = "test-id-123"
        
        mock_response_data = {
            "id": "job-123",
            "status": "IN_QUEUE"
        }
        
        # Mock template loading
        with patch.object(service, '_load_template', return_value=sample_template):
            # Mock aiohttp session and response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.text = AsyncMock(return_value=json.dumps(mock_response_data))
            
            # Create async context manager for post method
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=False)
            
            mock_session = AsyncMock()
            mock_session.post = Mock(return_value=mock_post_context)
            mock_session.closed = False
            
            with patch.object(service, '_get_session', return_value=mock_session):
                result = await service.generate_sticker(
                    prompt=prompt,
                    callback_url=callback_url,
                    processing_id=processing_id
                )
            
            assert result == mock_response_data
            
            # Verify POST request was made with correct payload
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args
            assert call_args[0][0] == "https://api.runpod.ai/v2/5ecx4u5xss6vi6/run"
            assert call_args[1]["headers"]["Content-Type"] == "application/json"
            
            # Verify payload contains substituted values
            payload = call_args[1]["json"]
            assert payload["input"]["prompt"] == prompt
            assert payload["input"]["processing_job_id"] == processing_id
            assert payload["input"]["callback_url"] == callback_url
    
    @allure.title("Generate sticker with auto-generated processing_id")
    @allure.description("Test sticker generation when processing_id is not provided")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_sticker_auto_id(self, service, sample_template):
        """Test sticker generation with auto-generated processing_id."""
        prompt = "happy robot"
        callback_url = "https://example.com/callback"
        
        mock_response_data = {"id": "job-123", "status": "IN_QUEUE"}
        
        # Mock template loading
        with patch.object(service, '_load_template', return_value=sample_template):
            # Mock aiohttp session and response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.text = AsyncMock(return_value=json.dumps(mock_response_data))
            
            # Create async context manager for post method
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=False)
            
            mock_session = AsyncMock()
            mock_session.post = Mock(return_value=mock_post_context)
            mock_session.closed = False
            
            with patch.object(service, '_get_session', return_value=mock_session):
                result = await service.generate_sticker(
                    prompt=prompt,
                    callback_url=callback_url,
                    processing_id=None
                )
            
            assert result == mock_response_data
            
            # Verify POST request was made
            call_args = mock_session.post.call_args
            payload = call_args[1]["json"]
            
            # processing_id should be a UUID string
            processing_id = payload["input"]["processing_job_id"]
            assert processing_id is not None
            # Validate it's a UUID format
            uuid.UUID(processing_id)
    
    @allure.title("Generate sticker - API error response")
    @allure.description("Test error handling when RunPod API returns error status")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_sticker_api_error(self, service, sample_template):
        """Test error handling when RunPod API returns error."""
        prompt = "cute cat"
        callback_url = "https://example.com/callback"
        
        # Mock template loading
        with patch.object(service, '_load_template', return_value=sample_template):
            # Mock aiohttp session with error response
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")
            mock_response.request_info = MagicMock()
            mock_response.history = ()
            
            # Create async context manager for post method
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=False)
            
            mock_session = AsyncMock()
            mock_session.post = Mock(return_value=mock_post_context)
            mock_session.closed = False
            
            with patch.object(service, '_get_session', return_value=mock_session):
                with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                    await service.generate_sticker(
                        prompt=prompt,
                        callback_url=callback_url
                    )
                
                assert exc_info.value.status == 500
    
    @allure.title("Generate sticker - invalid JSON response")
    @allure.description("Test error handling when RunPod API returns invalid JSON")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_generate_sticker_invalid_json(self, service, sample_template):
        """Test error handling when RunPod API returns invalid JSON."""
        prompt = "cute cat"
        callback_url = "https://example.com/callback"
        
        # Mock template loading
        with patch.object(service, '_load_template', return_value=sample_template):
            # Mock aiohttp session with invalid JSON response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
            mock_response.text = AsyncMock(return_value="Not valid JSON")
            
            # Create async context manager for post method
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=False)
            
            mock_session = AsyncMock()
            mock_session.post = Mock(return_value=mock_post_context)
            mock_session.closed = False
            
            with patch.object(service, '_get_session', return_value=mock_session):
                with pytest.raises(ValueError) as exc_info:
                    await service.generate_sticker(
                        prompt=prompt,
                        callback_url=callback_url
                    )
                
                assert "Invalid JSON response" in str(exc_info.value)
    
    @allure.title("Close session")
    @allure.description("Test closing aiohttp session")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test closing aiohttp session."""
        # Create mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        service._session = mock_session
        
        await service.close()
        
        mock_session.close.assert_called_once()

