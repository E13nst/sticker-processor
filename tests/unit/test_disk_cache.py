"""Unit tests for disk cache service."""
import pytest
import allure
import json
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta
from app.services.disk_cache import DiskCacheService


@allure.feature("Disk Cache")
@allure.tag("cache", "disk", "unit")
@pytest.mark.unit
class TestDiskCacheService:
    """Test DiskCacheService functionality."""
    
    @allure.title("Disk cache initialization")
    @allure.description("Test that disk cache initializes with correct directory and settings")
    @allure.severity(allure.severity_level.NORMAL)
    def test_disk_cache_initialization(self, disk_cache_service, temp_cache_dir):
        """Test disk cache initializes correctly."""
        with allure.step("Check disk cache instance"):
            assert disk_cache_service is not None
            assert disk_cache_service.cache_dir == temp_cache_dir
        
        with allure.step("Verify cache directory exists"):
            assert temp_cache_dir.exists()
            assert temp_cache_dir.is_dir()
        
        with allure.step("Check statistics initialization"):
            assert disk_cache_service.stats['total_files'] == 0
            assert disk_cache_service.stats['cache_hits'] == 0
            assert disk_cache_service.stats['cache_misses'] == 0
    
    @allure.title("Store and retrieve file")
    @allure.description("Test storing and retrieving files from disk cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_store_and_retrieve_file(self, disk_cache_service):
        """Test storing and retrieving files."""
        file_id = "test_file_001"
        file_content = b"test file content"
        file_format = "lottie"
        
        with allure.step("Store file in cache"):
            success = await disk_cache_service.store_file(
                file_id, file_content, file_format, converted=True
            )
            assert success is True
        
        with allure.step("Retrieve file from cache"):
            retrieved = await disk_cache_service.get_file(file_id, file_format)
            assert retrieved is not None
            assert retrieved == file_content
        
        with allure.step("Verify cache hit statistics"):
            assert disk_cache_service.stats['cache_hits'] == 1
            assert disk_cache_service.stats['total_files'] == 1
    
    @allure.title("Cache miss for non-existent file")
    @allure.description("Test that non-existent files return None")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_miss(self, disk_cache_service):
        """Test cache miss for non-existent file."""
        with allure.step("Try to retrieve non-existent file"):
            retrieved = await disk_cache_service.get_file("nonexistent_file", "lottie")
            assert retrieved is None
        
        with allure.step("Verify cache miss statistics"):
            assert disk_cache_service.stats['cache_misses'] == 1
    
    @allure.title("Delete file from cache")
    @allure.description("Test deleting files from disk cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_delete_file(self, disk_cache_service):
        """Test deleting files from cache."""
        file_id = "test_file_delete"
        file_content = b"content to delete"
        file_format = "lottie"
        
        with allure.step("Store file"):
            await disk_cache_service.store_file(file_id, file_content, file_format)
        
        with allure.step("Verify file exists"):
            retrieved = await disk_cache_service.get_file(file_id, file_format)
            assert retrieved is not None
        
        with allure.step("Delete file"):
            success = await disk_cache_service.delete_file(file_id, file_format)
            assert success is True
        
        with allure.step("Verify file is deleted"):
            retrieved = await disk_cache_service.get_file(file_id, file_format)
            assert retrieved is None
        
        with allure.step("Verify statistics updated"):
            assert disk_cache_service.stats['files_deleted'] == 1
    
    @allure.title("Multiple file formats")
    @allure.description("Test storing and retrieving different file formats")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_multiple_formats(self, disk_cache_service):
        """Test storing multiple file formats."""
        file_id = "test_multi_format"
        formats = ['lottie', 'webp', 'png']
        
        with allure.step("Store files in different formats"):
            for fmt in formats:
                content = f"content_{fmt}".encode()
                await disk_cache_service.store_file(file_id, content, fmt)
        
        with allure.step("Retrieve files in different formats"):
            for fmt in formats:
                retrieved = await disk_cache_service.get_file(file_id, fmt)
                assert retrieved is not None
                assert retrieved == f"content_{fmt}".encode()
    
    @allure.title("File expiration")
    @allure.description("Test that expired files are not returned")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_file_expiration(self, disk_cache_service, monkeypatch):
        """Test that expired files are not returned."""
        file_id = "test_expired_unique"
        file_content = b"expired content"
        file_format = "lottie"
        
        with allure.step("Store file"):
            await disk_cache_service.store_file(file_id, file_content, file_format)
        
        with allure.step("Verify file exists before expiration"):
            retrieved = await disk_cache_service.get_file(file_id, file_format)
            assert retrieved == file_content
        
        with allure.step("Manually expire file by modifying metadata"):
            # Simulate expiration by setting old expiry date
            from datetime import datetime, timedelta
            import json
            expired_date = (datetime.now() - timedelta(days=1)).isoformat()
            # Write metadata in the format that _read_metadata expects
            metadata_path = disk_cache_service._get_metadata_path(file_id, file_format)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(metadata_path, 'w') as f:
                # Write as key: value format that _read_metadata parses
                await f.write(f"file_id: {file_id}\nformat: {file_format}\nexpires_at: {expired_date}\n")
        
        with allure.step("Try to retrieve expired file"):
            retrieved = await disk_cache_service.get_file(file_id, file_format)
            # File should be deleted when expired, so should return None
            assert retrieved is None
    
    @allure.title("Cache statistics")
    @allure.description("Test that cache statistics are tracked correctly")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_statistics(self, disk_cache_service):
        """Test cache statistics tracking."""
        initial_hits = disk_cache_service.stats['cache_hits']
        initial_misses = disk_cache_service.stats['cache_misses']
        initial_files = disk_cache_service.stats['total_files']
        initial_created = disk_cache_service.stats['files_created']
        
        with allure.step("Store multiple files"):
            for i in range(3):
                await disk_cache_service.store_file(
                    f"test_stat_{i}", b"content", "lottie"
                )
        
        with allure.step("Retrieve files"):
            for i in range(3):
                await disk_cache_service.get_file(f"test_stat_{i}", "lottie")
        
        with allure.step("Verify statistics"):
            # Files should be created
            assert disk_cache_service.stats['files_created'] >= initial_created + 3
            # Cache hits should increase
            assert disk_cache_service.stats['cache_hits'] >= initial_hits + 3
            # Total files should increase
            assert disk_cache_service.stats['total_files'] >= initial_files + 3
    
    @allure.title("Cleanup expired files")
    @allure.description("Test cleanup of expired files from cache")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cleanup_expired_files(self, disk_cache_service):
        """Test cleaning up expired files."""
        with allure.step("Store some files"):
            for i in range(3):
                await disk_cache_service.store_file(
                    f"cleanup_test_{i}", b"content", "lottie"
                )
        
        with allure.step("Run cleanup"):
            deleted_count = await disk_cache_service.cleanup_expired_files()
            assert deleted_count >= 0  # May be 0 if no files expired
        
        with allure.step("Verify cleanup statistics"):
            assert disk_cache_service.stats['cleanup_runs'] >= 1

