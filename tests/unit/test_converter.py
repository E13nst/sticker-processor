"""Unit tests for converter service."""
import pytest
import allure
import gzip
import json
from app.services.converter import ConverterService


@allure.feature("Format Conversion")
@allure.tag("converter", "tgs", "lottie", "unit")
@pytest.mark.unit
class TestConverterService:
    """Test ConverterService functionality."""
    
    def test_converter_initialization(self, converter_service):
        """Test converter service initializes correctly."""
        assert converter_service is not None
        assert converter_service.timeout > 0
        assert hasattr(converter_service, 'lottie_available')
    
    def test_get_output_mime_type(self, converter_service):
        """Test MIME type mapping."""
        assert converter_service.get_output_mime_type('lottie') == 'application/json'
        assert converter_service.get_output_mime_type('webm') == 'video/webm'
        assert converter_service.get_output_mime_type('webp') == 'image/webp'
        assert converter_service.get_output_mime_type('png') == 'image/png'
        assert converter_service.get_output_mime_type('jpg') == 'image/jpeg'
        assert converter_service.get_output_mime_type('tgs') == 'application/gzip'
        assert converter_service.get_output_mime_type('unknown') == 'application/octet-stream'
    
    def test_is_valid_lottie(self, converter_service):
        """Test Lottie validation."""
        # Valid Lottie
        valid_lottie = {
            'v': '5.5.7',
            'fr': 60,
            'w': 512,
            'h': 512
        }
        assert converter_service._is_valid_lottie(valid_lottie) is True
        
        # Invalid Lottie (missing required fields)
        invalid_lottie = {'v': '5.5.7'}
        assert converter_service._is_valid_lottie(invalid_lottie) is False
    
    @pytest.mark.asyncio
    async def test_convert_gzip_sync_valid(self, converter_service, sample_tgs_content):
        """Test synchronous gzip conversion with valid TGS."""
        result = converter_service._convert_gzip_sync(sample_tgs_content)
        
        assert result is not None
        output_format, content = result
        assert output_format == 'lottie'
        assert isinstance(content, bytes)
        
        # Verify it's valid JSON
        lottie_data = json.loads(content.decode('utf-8'))
        assert 'v' in lottie_data
        assert 'fr' in lottie_data
    
    @pytest.mark.asyncio
    async def test_convert_gzip_sync_invalid(self, converter_service):
        """Test synchronous gzip conversion with invalid data."""
        invalid_data = b"not gzipped data"
        result = converter_service._convert_gzip_sync(invalid_data)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_process_sticker_tgs(self, converter_service, sample_tgs_content):
        """Test processing TGS sticker."""
        output_format, content, was_converted = await converter_service.process_sticker(
            sample_tgs_content, 'tgs'
        )
        
        assert output_format == 'lottie'
        assert isinstance(content, bytes)
        assert was_converted is True
    
    @pytest.mark.asyncio
    async def test_process_sticker_webp(self, converter_service):
        """Test processing WebP sticker (no conversion)."""
        webp_content = b"fake webp content"
        output_format, content, was_converted = await converter_service.process_sticker(
            webp_content, 'webp'
        )
        
        assert output_format == 'webp'
        assert content == webp_content
        assert was_converted is False
    
    @pytest.mark.asyncio
    async def test_process_sticker_fallback(self, converter_service):
        """Test fallback when TGS conversion fails."""
        invalid_tgs = b"invalid tgs content"
        output_format, content, was_converted = await converter_service.process_sticker(
            invalid_tgs, 'tgs'
        )
        
        # Should return original on failure
        assert output_format == 'tgs'
        assert content == invalid_tgs
        assert was_converted is False

