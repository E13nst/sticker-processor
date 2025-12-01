"""Unit tests for Telegram service."""
import pytest
import allure
from app.services.telegram_enhanced import TelegramServiceEnhanced


@allure.feature("Telegram Service")
@allure.tag("telegram", "api", "unit")
@pytest.mark.unit
class TestTelegramService:
    """Test TelegramService functionality."""
    
    def test_telegram_service_initialization(self, telegram_service):
        """Test Telegram service initializes correctly."""
        assert telegram_service is not None
        assert telegram_service.bot_token is not None
        assert telegram_service.api_base_url == "https://api.telegram.org"
        assert hasattr(telegram_service, 'stats')
    
    def test_detect_file_format_by_extension(self, telegram_service):
        """Test file format detection by extension."""
        assert telegram_service.detect_file_format("file.tgs", b"") == 'tgs'
        assert telegram_service.detect_file_format("file.webm", b"") == 'webm'
        assert telegram_service.detect_file_format("file.webp", b"") == 'webp'
        assert telegram_service.detect_file_format("file.png", b"") == 'png'
        assert telegram_service.detect_file_format("file.jpg", b"") == 'jpg'
        assert telegram_service.detect_file_format("file.jpeg", b"") == 'jpg'
    
    def test_detect_file_format_by_magic_bytes(self, telegram_service):
        """Test file format detection by magic bytes."""
        # TGS (gzip)
        assert telegram_service.detect_file_format("file", b'\x1f\x8b\x08\x00') == 'tgs'
        
        # WebP
        webp_header = b'RIFF\x00\x00\x00\x00WEBP'
        assert telegram_service.detect_file_format("file", webp_header) == 'webp'
        
        # PNG
        assert telegram_service.detect_file_format("file", b'\x89PNG\r\n\x1a\n') == 'png'
        
        # JPEG
        assert telegram_service.detect_file_format("file", b'\xff\xd8\xff\xe0') == 'jpg'
        
        # Unknown
        assert telegram_service.detect_file_format("file", b'unknown') == 'unknown'
    
    def test_get_mime_type(self, telegram_service):
        """Test MIME type retrieval."""
        assert telegram_service.get_mime_type('tgs') == 'application/gzip'
        assert telegram_service.get_mime_type('webm') == 'video/webm'
        assert telegram_service.get_mime_type('webp') == 'image/webp'
        assert telegram_service.get_mime_type('png') == 'image/png'
        assert telegram_service.get_mime_type('jpg') == 'image/jpeg'
        assert telegram_service.get_mime_type('lottie') == 'application/json'
        assert telegram_service.get_mime_type('unknown') == 'application/octet-stream'
    
    def test_statistics_initialization(self, telegram_service):
        """Test statistics are initialized correctly."""
        stats = telegram_service.get_statistics()
        assert stats['total_requests'] == 0
        assert stats['successful_requests'] == 0
        assert stats['failed_requests'] == 0
        assert stats['total_bytes_downloaded'] == 0
        assert isinstance(stats['errors_by_type'], dict)
    
    def test_record_success(self, telegram_service):
        """Test recording successful request."""
        telegram_service._record_success(100, 1024)
        stats = telegram_service.get_statistics()
        
        assert stats['total_requests'] == 1
        assert stats['successful_requests'] == 1
        assert stats['failed_requests'] == 0
        assert stats['total_bytes_downloaded'] == 1024
        assert stats['total_download_time_ms'] == 100
    
    def test_record_error(self, telegram_service):
        """Test recording failed request."""
        telegram_service._record_error('HTTP_404_NOT_FOUND', 150)
        stats = telegram_service.get_statistics()
        
        assert stats['total_requests'] == 1
        assert stats['successful_requests'] == 0
        assert stats['failed_requests'] == 1
        assert stats['total_download_time_ms'] == 150
        assert stats['errors_by_type']['HTTP_404_NOT_FOUND'] == 1
    
    def test_multiple_error_tracking(self, telegram_service):
        """Test tracking multiple errors of same type."""
        telegram_service._record_error('TIMEOUT', 100)
        telegram_service._record_error('TIMEOUT', 200)
        telegram_service._record_error('HTTP_500', 150)
        
        stats = telegram_service.get_statistics()
        assert stats['errors_by_type']['TIMEOUT'] == 2
        assert stats['errors_by_type']['HTTP_500'] == 1

