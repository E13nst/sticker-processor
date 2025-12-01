"""Unit tests for sticker handler combine_sticker_set functionality."""
import pytest
import allure
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import HTTPException
from PIL import Image
import io

from app.handlers.sticker_handler import StickerHandler
from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError


@allure.feature("Sticker Handler")
@allure.tag("sticker-handler", "combine-set", "unit")
@pytest.mark.unit
class TestStickerHandlerCombineSet:
    """Test StickerHandler combine_sticker_set functionality."""
    
    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        manager = Mock(spec=CacheManager)
        manager.get_sticker_set = AsyncMock()
        manager.get_sticker = AsyncMock()
        return manager
    
    @pytest.fixture
    def handler(self, mock_cache_manager):
        """Create sticker handler with mock cache manager."""
        return StickerHandler(mock_cache_manager)
    
    @pytest.fixture
    def sample_sticker_set(self):
        """Sample sticker set data."""
        return {
            "name": "test_set",
            "title": "Test Set",
            "stickers": [
                {
                    "file_id": "file1",
                    "emoji": "😀",
                    "thumbnail": {"file_id": "thumb1"},
                    "thumb": {"file_id": "thumb1"}
                },
                {
                    "file_id": "file2",
                    "emoji": "😃",
                    "thumbnail": {"file_id": "thumb2"},
                    "thumb": {"file_id": "thumb2"}
                }
            ]
        }
    
    @pytest.fixture
    def sample_image_bytes(self):
        """Sample image bytes (PNG)."""
        img = Image.new('RGB', (100, 100), color='red')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    
    @allure.title("Combine sticker set with main images")
    @allure.description("Test combining stickers from set using main images")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_main_images(self, handler, mock_cache_manager, sample_sticker_set, sample_image_bytes):
        """Test combining sticker set with main images."""
        # Mock cache manager responses
        mock_cache_manager.get_sticker_set.return_value = sample_sticker_set
        mock_cache_manager.get_sticker.return_value = (sample_image_bytes, "image/png", False)
        
        result = await handler.combine_sticker_set(
            name="test_set",
            image_type="main",
            tile_size=128
        )
        
        assert result is not None
        assert result.status_code == 200
        assert result.media_type == "image/webp"
        
        # Verify headers (case-insensitive)
        headers = dict(result.headers)
        headers_lower = {k.lower(): v for k, v in headers.items()}
        assert "x-images-combined" in headers_lower
        assert "x-sticker-set-name" in headers_lower
        assert headers_lower["x-sticker-set-name"] == "test_set"
        assert headers_lower["x-image-type"] == "main"
        
        # Verify cache manager was called
        mock_cache_manager.get_sticker_set.assert_called_once_with("test_set")
        assert mock_cache_manager.get_sticker.call_count == 2  # Two stickers
    
    @allure.title("Combine sticker set with thumbnails")
    @allure.description("Test combining stickers from set using thumbnail images")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_thumbnails(self, handler, mock_cache_manager, sample_sticker_set, sample_image_bytes):
        """Test combining sticker set with thumbnails."""
        mock_cache_manager.get_sticker_set.return_value = sample_sticker_set
        mock_cache_manager.get_sticker.return_value = (sample_image_bytes, "image/png", False)
        
        result = await handler.combine_sticker_set(
            name="test_set",
            image_type="thumbnail",
            tile_size=128
        )
        
        assert result is not None
        assert result.status_code == 200
        
        headers = dict(result.headers)
        headers_lower = {k.lower(): v for k, v in headers.items()}
        assert headers_lower["x-image-type"] == "thumbnail"
        
        # Should use thumbnail file_ids
        calls = [call[0][0] for call in mock_cache_manager.get_sticker.call_args_list]
        assert "thumb1" in calls
        assert "thumb2" in calls
    
    @allure.title("Combine sticker set with max_stickers limit")
    @allure.description("Test limiting number of stickers processed")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_max_stickers(self, handler, mock_cache_manager, sample_sticker_set, sample_image_bytes):
        """Test combining sticker set with max_stickers limit."""
        # Add more stickers
        sample_sticker_set["stickers"].extend([
            {"file_id": "file3", "emoji": "😄"},
            {"file_id": "file4", "emoji": "😁"}
        ])
        
        mock_cache_manager.get_sticker_set.return_value = sample_sticker_set
        mock_cache_manager.get_sticker.return_value = (sample_image_bytes, "image/png", False)
        
        result = await handler.combine_sticker_set(
            name="test_set",
            image_type="main",
            tile_size=128,
            max_stickers=2
        )
        
        assert result is not None
        assert result.status_code == 200
        
        # Should only process 2 stickers
        assert mock_cache_manager.get_sticker.call_count == 2
        
        headers = dict(result.headers)
        headers_lower = {k.lower(): v for k, v in headers.items()}
        assert int(headers_lower["x-images-combined"]) == 2
    
    @allure.title("Combine sticker set handles missing set")
    @allure.description("Test handling missing sticker set")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_not_found(self, handler, mock_cache_manager):
        """Test handling missing sticker set."""
        mock_cache_manager.get_sticker_set.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await handler.combine_sticker_set(name="nonexistent", image_type="main")
        
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()
    
    @allure.title("Combine sticker set handles empty set")
    @allure.description("Test handling sticker set with no stickers")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_empty(self, handler, mock_cache_manager):
        """Test handling empty sticker set."""
        mock_cache_manager.get_sticker_set.return_value = {
            "name": "empty_set",
            "stickers": []
        }
        
        with pytest.raises(HTTPException) as exc_info:
            await handler.combine_sticker_set(name="empty_set", image_type="main")
        
        assert exc_info.value.status_code == 404
        assert "no stickers" in exc_info.value.detail.lower()
    
    @allure.title("Combine sticker set handles missing image type")
    @allure.description("Test handling stickers without requested image type")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_sticker_set_missing_image_type(self, handler, mock_cache_manager, sample_image_bytes):
        """Test handling stickers without requested image type."""
        sticker_set = {
            "name": "test_set",
            "stickers": [
                {"file_id": "file1"},  # Has main
                {"emoji": "😀"}  # No file_id
            ]
        }
        
        mock_cache_manager.get_sticker_set.return_value = sticker_set
        mock_cache_manager.get_sticker.return_value = (sample_image_bytes, "image/png", False)
        
        result = await handler.combine_sticker_set(
            name="test_set",
            image_type="main",
            tile_size=128
        )
        
        # Should process only the sticker with file_id
        assert mock_cache_manager.get_sticker.call_count == 1
        assert result.status_code == 200
        headers = dict(result.headers)
        headers_lower = {k.lower(): v for k, v in headers.items()}
        assert int(headers_lower["x-images-combined"]) == 1

