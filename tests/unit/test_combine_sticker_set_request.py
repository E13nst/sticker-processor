"""Unit tests for CombineStickerSetRequest model."""
import pytest
import allure
from pydantic import ValidationError

from app.models.requests import CombineStickerSetRequest


@allure.feature("Request Models")
@allure.tag("models", "validation", "unit")
@pytest.mark.unit
class TestCombineStickerSetRequest:
    """Test CombineStickerSetRequest model validation."""
    
    @allure.title("Valid request with name")
    @allure.description("Test valid request with sticker set name")
    @allure.severity(allure.severity_level.NORMAL)
    def test_valid_request_with_name(self):
        """Test valid request with name."""
        request = CombineStickerSetRequest(
            name="test_set",
            image_type="main",
            tile_size=128
        )
        
        assert request.name == "test_set"
        assert request.image_type == "main"
        assert request.tile_size == 128
        assert request.max_stickers is None
    
    @allure.title("Valid request with URL")
    @allure.description("Test valid request with sticker set URL")
    @allure.severity(allure.severity_level.NORMAL)
    def test_valid_request_with_url(self):
        """Test valid request with URL."""
        request = CombineStickerSetRequest(
            url="https://t.me/addstickers/test_set",
            image_type="thumbnail"
        )
        
        # Name should be extracted from URL
        assert request.name == "test_set"
        assert request.url == "https://t.me/addstickers/test_set"
        assert request.image_type == "thumbnail"
    
    @allure.title("Extract name from URL")
    @allure.description("Test extracting sticker set name from URL")
    @allure.severity(allure.severity_level.NORMAL)
    def test_extract_name_from_url(self):
        """Test extracting name from URL."""
        request = CombineStickerSetRequest(
            url="https://t.me/addstickers/arcticfox"
        )
        
        assert request.name == "arcticfox"
    
    @allure.title("Invalid URL format")
    @allure.description("Test validation rejects invalid URL format")
    @allure.severity(allure.severity_level.NORMAL)
    def test_invalid_url_format(self):
        """Test invalid URL format."""
        with pytest.raises(ValidationError) as exc_info:
            CombineStickerSetRequest(url="https://invalid.url/test")
        
        errors = exc_info.value.errors()
        assert any("Invalid sticker set URL format" in str(error.get("msg", "")) for error in errors)
    
    @allure.title("Missing name and URL")
    @allure.description("Test validation requires either name or URL")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_missing_name_and_url(self):
        """Test missing both name and URL."""
        with pytest.raises(ValidationError) as exc_info:
            CombineStickerSetRequest(image_type="main")
        
        errors = exc_info.value.errors()
        assert any("Either 'name' or 'url' must be provided" in str(error.get("msg", "")) for error in errors)
    
    @allure.title("Invalid image type")
    @allure.description("Test validation rejects invalid image type")
    @allure.severity(allure.severity_level.NORMAL)
    def test_invalid_image_type(self):
        """Test invalid image type."""
        with pytest.raises(ValidationError) as exc_info:
            CombineStickerSetRequest(name="test", image_type="invalid")
        
        errors = exc_info.value.errors()
        assert any("image_type must be one of" in str(error.get("msg", "")) for error in errors)
    
    @allure.title("Valid image types")
    @allure.description("Test all valid image types")
    @allure.severity(allure.severity_level.NORMAL)
    def test_valid_image_types(self):
        """Test all valid image types."""
        for image_type in ["main", "thumbnail", "thumb"]:
            request = CombineStickerSetRequest(name="test", image_type=image_type)
            assert request.image_type == image_type
    
    @allure.title("Max stickers validation")
    @allure.description("Test max_stickers parameter validation")
    @allure.severity(allure.severity_level.NORMAL)
    def test_max_stickers_validation(self):
        """Test max_stickers validation."""
        # Valid max_stickers
        request = CombineStickerSetRequest(name="test", max_stickers=50)
        assert request.max_stickers == 50
        
        # Invalid: too small
        with pytest.raises(ValidationError):
            CombineStickerSetRequest(name="test", max_stickers=0)
        
        # Invalid: too large
        with pytest.raises(ValidationError):
            CombineStickerSetRequest(name="test", max_stickers=2000)
    
    @allure.title("Tile size validation")
    @allure.description("Test tile_size parameter validation")
    @allure.severity(allure.severity_level.NORMAL)
    def test_tile_size_validation(self):
        """Test tile_size validation."""
        # Valid tile_size
        request = CombineStickerSetRequest(name="test", tile_size=256)
        assert request.tile_size == 256
        
        # Invalid: too small
        with pytest.raises(ValidationError):
            CombineStickerSetRequest(name="test", tile_size=0)
        
        # Invalid: too large
        with pytest.raises(ValidationError):
            CombineStickerSetRequest(name="test", tile_size=3000)
    
    @allure.title("Name and URL conflict")
    @allure.description("Test handling when both name and URL are provided")
    @allure.severity(allure.severity_level.MINOR)
    def test_name_and_url_both_provided(self):
        """Test when both name and URL are provided."""
        # URL should take precedence
        request = CombineStickerSetRequest(
            name="different_name",
            url="https://t.me/addstickers/test_set"
        )
        
        # Name should be extracted from URL
        assert request.name == "test_set"
    
    @allure.title("Default values")
    @allure.description("Test default parameter values")
    @allure.severity(allure.severity_level.MINOR)
    def test_default_values(self):
        """Test default values."""
        request = CombineStickerSetRequest(name="test")
        
        assert request.image_type == "main"
        assert request.tile_size == 128
        assert request.max_stickers is None

