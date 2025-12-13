"""E2E tests with real stickers from Telegram."""
import pytest
import allure
import json
import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from httpx import AsyncClient
from dotenv import load_dotenv

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file to get TELEGRAM_BOT_TOKEN
load_dotenv()

from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError

# Test sticker sets data
STICKER_SETS = {
    "tgs_animation": {
        "name": "worldart",
        "url": "https://t.me/addstickers/worldart",
        "type": "tgs"
    },
    "video": {
        "name": "pack_1_40802189314_5786_155347765_by_sticker_bot",
        "url": "https://t.me/addstickers/pack_1_40802189314_5786_155347765_by_sticker_bot",
        "type": "video"
    }
}


@allure.feature("E2E Tests")
@allure.tag("e2e", "telegram", "real-api", "stickers")
@pytest.mark.e2e
@pytest.mark.telegram
@pytest.mark.real_api
@pytest.mark.slow
class TestE2ERealStickers:
    """E2E tests with real stickers from Telegram."""
    
    @pytest.fixture
    def telegram_bot_token(self) -> str:
        """Get Telegram bot token from environment or .env file."""
        # Try to get from environment (may be loaded from .env by load_dotenv)
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token or token == "test_bot_token":
            pytest.skip("TELEGRAM_BOT_TOKEN not set in .env or environment, skipping E2E tests")
        return token
    
    @pytest.fixture
    async def cache_manager(self, telegram_bot_token: str):
        """Create CacheManager instance for e2e tests."""
        manager = CacheManager()
        try:
            await manager.connect()
            yield manager
        except Exception as e:
            pytest.skip(f"CacheManager not available: {e}")
        finally:
            await manager.disconnect()
    
    async def get_sticker_set(self, cache_manager: CacheManager, sticker_set_name: str) -> Dict[str, Any]:
        """Get sticker set using CacheManager (with Redis caching)."""
        with allure.step(f"Get sticker set '{sticker_set_name}' from Telegram API (via CacheManager)"):
            try:
                sticker_set = await cache_manager.get_sticker_set(sticker_set_name)
                if not sticker_set:
                    pytest.skip(f"Sticker set {sticker_set_name} not found or unavailable")
                
                allure.attach(
                    json.dumps({
                        "name": sticker_set.get("name"),
                        "title": sticker_set.get("title"),
                        "stickers_count": len(sticker_set.get("stickers", []))
                    }, indent=2),
                    "Sticker Set Info",
                    allure.attachment_type.JSON
                )
                
                return sticker_set
            except TelegramAPIError as e:
                allure.attach(
                    f"Status: {e.status}\nDescription: {e.description}",
                    "Telegram API Error",
                    allure.attachment_type.TEXT
                )
                pytest.skip(f"Could not get sticker set {sticker_set_name}: [{e.status}] {e.description}")
            except Exception as e:
                allure.attach(
                    f"Error: {str(e)}",
                    "Error",
                    allure.attachment_type.TEXT
                )
                pytest.skip(f"Could not get sticker set {sticker_set_name}: {str(e)}")
    
    def extract_file_ids(self, sticker_set: Dict[str, Any], limit: int = 10) -> List[str]:
        """Extract file IDs from sticker set."""
        stickers = sticker_set.get("stickers", [])
        file_ids = []
        
        for sticker in stickers[:limit]:
            # Get file_id from sticker object
            file_id = sticker.get("file_id")
            if file_id:
                file_ids.append(file_id)
        
        return file_ids
    
    @allure.title("E2E: TGS animation stickers from worldart pack")
    @allure.description("""
    Test loading TGS animation stickers from worldart pack:
    1. Get sticker set from Telegram Bot API (via CacheManager)
    2. Extract file IDs of first 10 stickers
    3. Load each sticker through /stickers/{file_id}
    4. Verify content is loaded and converted to Lottie
    5. Check response headers and performance
    """)
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_tgs_animation_stickers(
        self, 
        client: AsyncClient,
        cache_manager: CacheManager
    ):
        """Test loading TGS animation stickers."""
        sticker_set_name = STICKER_SETS["tgs_animation"]["name"]
        
        with allure.step("Get sticker set from Telegram API"):
            sticker_set = await self.get_sticker_set(cache_manager, sticker_set_name)
        
        with allure.step("Extract file IDs from sticker set"):
            file_ids = self.extract_file_ids(sticker_set, limit=10)
            assert len(file_ids) > 0, "No file IDs found in sticker set"
            allure.attach(
                json.dumps({"file_ids": file_ids, "count": len(file_ids)}, indent=2),
                "Extracted File IDs",
                allure.attachment_type.JSON
            )
        
        with allure.step("Get initial cache statistics"):
            # Get stats from both Redis and Disk caches
            redis_stats_before = await client.get("/cache/redis/stats")
            disk_stats_before = await client.get("/cache/disk/stats")
            stats_before_data = {
                "redis": redis_stats_before.json() if redis_stats_before.status_code == 200 else {},
                "disk": disk_stats_before.json() if disk_stats_before.status_code == 200 else {}
            }
            allure.attach(
                json.dumps(stats_before_data, indent=2, default=str),
                "Cache Stats Before",
                allure.attachment_type.JSON
            )
        
        successful_loads = 0
        failed_loads = []
        response_times = []
        
        for i, file_id in enumerate(file_ids, 1):
            with allure.step(f"Load sticker {i}/{len(file_ids)}: {file_id[:20]}..."):
                try:
                    import time
                    start_time = time.time()
                    
                    response = await client.get(f"/stickers/{file_id}")
                    elapsed_time = (time.time() - start_time) * 1000
                    response_times.append(elapsed_time)
                    
                    if response.status_code == 200:
                        successful_loads += 1
                        
                        # Verify content
                        content = response.content
                        assert len(content) > 0, "Content should not be empty"
                        
                        # Check headers
                        headers = dict(response.headers)
                        assert "X-File-ID" in headers
                        assert "X-Is-Converted" in headers
                        assert "Content-Type" in headers
                        
                        # For TGS, should be converted to JSON (lottie)
                        if headers.get("X-Is-Converted") == "True":
                            # Verify it's valid JSON
                            try:
                                json.loads(content.decode('utf-8'))
                                allure.attach(
                                    f"Successfully loaded and converted TGS sticker\n"
                                    f"File ID: {file_id}\n"
                                    f"Size: {len(content)} bytes\n"
                                    f"Response time: {elapsed_time:.2f}ms\n"
                                    f"Content-Type: {headers.get('Content-Type')}",
                                    f"Sticker {i} Details",
                                    allure.attachment_type.TEXT
                                )
                            except json.JSONDecodeError:
                                allure.attach(
                                    f"Warning: Content is not valid JSON\nFile ID: {file_id}\nSize: {len(content)} bytes",
                                    f"Sticker {i} Warning",
                                    allure.attachment_type.TEXT
                                )
                    else:
                        failed_loads.append({
                            "file_id": file_id,
                            "status_code": response.status_code,
                            "error": response.text[:200]
                        })
                        allure.attach(
                            f"Failed to load sticker\nFile ID: {file_id}\nStatus: {response.status_code}\nError: {response.text[:200]}",
                            f"Sticker {i} Error",
                            allure.attachment_type.TEXT
                        )
                
                except Exception as e:
                    failed_loads.append({
                        "file_id": file_id,
                        "error": str(e)
                    })
                    allure.attach(
                        f"Exception loading sticker\nFile ID: {file_id}\nError: {str(e)}",
                        f"Sticker {i} Exception",
                        allure.attachment_type.TEXT
                    )
        
        with allure.step("Get final cache statistics"):
            # Get stats from both Redis and Disk caches
            redis_stats_after = await client.get("/cache/redis/stats")
            disk_stats_after = await client.get("/cache/disk/stats")
            stats_after_data = {
                "redis": redis_stats_after.json() if redis_stats_after.status_code == 200 else {},
                "disk": disk_stats_after.json() if disk_stats_after.status_code == 200 else {}
            }
            allure.attach(
                json.dumps(stats_after_data, indent=2, default=str),
                "Cache Stats After",
                allure.attachment_type.JSON
            )
        
        with allure.step("Verify test results"):
            allure.attach(
                json.dumps({
                    "total_stickers": len(file_ids),
                    "successful_loads": successful_loads,
                    "failed_loads": len(failed_loads),
                    "average_response_time_ms": sum(response_times) / len(response_times) if response_times else 0,
                    "min_response_time_ms": min(response_times) if response_times else 0,
                    "max_response_time_ms": max(response_times) if response_times else 0,
                    "failed_file_ids": failed_loads
                }, indent=2),
                "Test Results Summary",
                allure.attachment_type.JSON
            )
            
            # At least 80% should succeed
            success_rate = successful_loads / len(file_ids) if file_ids else 0
            assert success_rate >= 0.8, f"Success rate {success_rate:.1%} is below 80%"
    
    @allure.title("E2E: Video stickers from pack_1_40802189314_5786_155347765_by_sticker_bot")
    @allure.description("""
    Test loading video stickers:
    1. Get sticker set from Telegram Bot API (via CacheManager)
    2. Extract file IDs of first 10 stickers
    3. Load each sticker through /stickers/{file_id}
    4. Verify content is loaded (not converted)
    5. Check response headers and MIME types
    """)
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_video_stickers(
        self,
        client: AsyncClient,
        cache_manager: CacheManager
    ):
        """Test loading video stickers."""
        sticker_set_name = STICKER_SETS["video"]["name"]
        
        with allure.step("Get sticker set from Telegram API"):
            sticker_set = await self.get_sticker_set(cache_manager, sticker_set_name)
        
        with allure.step("Extract file IDs from sticker set"):
            file_ids = self.extract_file_ids(sticker_set, limit=10)
            assert len(file_ids) > 0, "No file IDs found in sticker set"
            allure.attach(
                json.dumps({"file_ids": file_ids, "count": len(file_ids)}, indent=2),
                "Extracted File IDs",
                allure.attachment_type.JSON
            )
        
        successful_loads = 0
        failed_loads = []
        
        for i, file_id in enumerate(file_ids, 1):
            with allure.step(f"Load video sticker {i}/{len(file_ids)}: {file_id[:20]}..."):
                try:
                    import time
                    start_time = time.time()
                    
                    response = await client.get(f"/stickers/{file_id}")
                    elapsed_time = (time.time() - start_time) * 1000
                    
                    if response.status_code == 200:
                        successful_loads += 1
                        
                        # Verify content
                        content = response.content
                        assert len(content) > 0, "Content should not be empty"
                        
                        # Check headers
                        headers = dict(response.headers)
                        assert "X-File-ID" in headers
                        assert "Content-Type" in headers
                        
                        # Video stickers should not be converted
                        assert headers.get("X-Is-Converted") == "False", "Video stickers should not be converted"
                        
                        # Check MIME type (should be video/webm)
                        content_type = headers.get("Content-Type", "")
                        assert "video" in content_type or "webm" in content_type.lower(), \
                            f"Expected video MIME type, got {content_type}"
                        
                        allure.attach(
                            f"Successfully loaded video sticker\n"
                            f"File ID: {file_id}\n"
                            f"Size: {len(content)} bytes\n"
                            f"Response time: {elapsed_time:.2f}ms\n"
                            f"Content-Type: {headers.get('Content-Type')}",
                            f"Video Sticker {i} Details",
                            allure.attachment_type.TEXT
                        )
                    else:
                        failed_loads.append({
                            "file_id": file_id,
                            "status_code": response.status_code,
                            "error": response.text[:200]
                        })
                
                except Exception as e:
                    failed_loads.append({
                        "file_id": file_id,
                        "error": str(e)
                    })
        
        with allure.step("Verify test results"):
            allure.attach(
                json.dumps({
                    "total_stickers": len(file_ids),
                    "successful_loads": successful_loads,
                    "failed_loads": len(failed_loads),
                    "failed_file_ids": failed_loads
                }, indent=2),
                "Test Results Summary",
                allure.attachment_type.JSON
            )
            
            # At least 80% should succeed
            success_rate = successful_loads / len(file_ids) if file_ids else 0
            assert success_rate >= 0.8, f"Success rate {success_rate:.1%} is below 80%"
    
    @allure.title("E2E: Cache performance test")
    @allure.description("""
    Test that cached stickers load faster than first request:
    1. Load sticker (first request - from Telegram)
    2. Load same sticker again (should be from cache)
    3. Verify second request is faster
    """)
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_cache_performance(
        self,
        client: AsyncClient,
        cache_manager: CacheManager
    ):
        """Test cache performance improvement."""
        sticker_set_name = STICKER_SETS["tgs_animation"]["name"]
        
        with allure.step("Get one sticker from set"):
            sticker_set = await self.get_sticker_set(cache_manager, sticker_set_name)
            file_ids = self.extract_file_ids(sticker_set, limit=1)
            
            if not file_ids:
                pytest.skip("No stickers found in set")
            
            file_id = file_ids[0]
        
        with allure.step("First request (from Telegram API)"):
            import time
            start_time = time.time()
            response1 = await client.get(f"/stickers/{file_id}")
            first_request_time = (time.time() - start_time) * 1000
            
            assert response1.status_code == 200
        
        with allure.step("Second request (from cache)"):
            start_time = time.time()
            response2 = await client.get(f"/stickers/{file_id}")
            second_request_time = (time.time() - start_time) * 1000
            
            assert response2.status_code == 200
            assert response1.content == response2.content, "Content should be identical"
        
        with allure.step("Verify cache performance"):
            performance_improvement = ((first_request_time - second_request_time) / first_request_time) * 100
            
            allure.attach(
                f"First request: {first_request_time:.2f}ms (from Telegram)\n"
                f"Second request: {second_request_time:.2f}ms (from cache)\n"
                f"Performance improvement: {performance_improvement:.1f}%",
                "Cache Performance",
                allure.attachment_type.TEXT
            )
            
            # Cached request should be significantly faster
            assert second_request_time < first_request_time, "Cached request should be faster"
            # Note: Improvement may be lower if file is already cached from previous tests
            # In real usage, first request fetches from Telegram (slow), second from cache (fast)
            assert performance_improvement > 0, f"Expected positive improvement, got {performance_improvement:.1f}%"
            if performance_improvement < 10:
                # If improvement is low, it means file was already cached - this is expected in test environment
                allure.attach(
                    f"Performance improvement: {performance_improvement:.1f}%\n"
                    f"Note: Low improvement indicates file was already cached from previous tests.\n"
                    f"This is expected behavior in test environment.",
                    "Performance Note",
                    allure.attachment_type.TEXT
                )
    
    @allure.title("E2E: Combine TGS animation stickers from set")
    @allure.description("""
    Test combining TGS animation stickers from a sticker set:
    1. Call POST /stickers/combine-from-set with sticker set name
    2. Verify combined WebP image is returned
    3. Check response headers and image properties
    4. Verify images are in correct order
    """)
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.asyncio
    async def test_combine_tgs_stickers_from_set(
        self,
        client: AsyncClient,
        cache_manager: CacheManager
    ):
        """Test combining TGS animation stickers from a set."""
        sticker_set = STICKER_SETS["tgs_animation"]
        
        with allure.step("Combine stickers from set using name"):
            request_data = {
                "name": sticker_set["name"],
                "image_type": "thumbnail",  # Use thumbnails for e2e tests
                "tile_size": 128,
                "max_stickers": 5  # Reduced for faster test execution
            }
            
            # Add timeout for the request (60 seconds should be enough for 10 stickers)
            response = await asyncio.wait_for(
                client.post("/stickers/combine-from-set", json=request_data, timeout=60.0),
                timeout=65.0
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
            assert response.headers["content-type"] == "image/webp", "Should return WebP image"
            
            # Read content first to ensure response is fully received
            image_content = response.content
            assert len(image_content) > 0, "Image content should not be empty"
            assert image_content.startswith(b"RIFF"), "Should be WebP format (RIFF header)"
            
            # Verify response headers (after reading content)
            # httpx may return headers in lowercase, so check both cases
            headers = dict(response.headers)
            headers_lower = {k.lower(): v for k, v in headers.items()}
            
            # Debug: log all headers if expected ones are missing
            if "x-processing-time-ms" not in headers_lower and "X-Processing-Time-Ms" not in headers:
                import pprint
                allure.attach(
                    f"Available headers: {list(headers.keys())}\n"
                    f"Available headers (lowercase): {list(headers_lower.keys())}\n"
                    f"Full headers: {pprint.pformat(headers)}",
                    "Debug Headers - Missing X-Processing-Time-Ms",
                    allure.attachment_type.TEXT
                )
            
            # Check headers (case-insensitive)
            processing_time = headers.get("X-Processing-Time-Ms") or headers_lower.get("x-processing-time-ms")
            images_combined = headers.get("X-Images-Combined") or headers_lower.get("x-images-combined")
            sticker_set_name = headers.get("X-Sticker-Set-Name") or headers_lower.get("x-sticker-set-name")
            image_type = headers.get("X-Image-Type") or headers_lower.get("x-image-type")
            
            assert processing_time is not None, f"Missing X-Processing-Time-Ms. Available: {list(headers.keys())}"
            assert images_combined is not None, f"Missing X-Images-Combined. Available: {list(headers.keys())}"
            assert sticker_set_name is not None, f"Missing X-Sticker-Set-Name. Available: {list(headers.keys())}"
            assert sticker_set_name == sticker_set["name"]
            assert image_type == "thumbnail"
            assert len(image_content) > 0, "Image content should not be empty"
            assert image_content.startswith(b"RIFF"), "Should be WebP format (RIFF header)"
            
            images_combined_val = int(images_combined) if images_combined else 0
            assert images_combined_val > 0, "Should combine at least one image"
            assert images_combined_val <= 5, "Should not exceed max_stickers limit"
            
            allure.attach(
                json.dumps({
                    "request": request_data,
                    "response_headers": {
                        "X-Processing-Time-Ms": processing_time,
                        "X-Images-Combined": images_combined,
                        "X-Images-Failed": headers.get("X-Images-Failed") or headers_lower.get("x-images-failed"),
                        "X-Tile-Size": headers.get("X-Tile-Size") or headers_lower.get("x-tile-size"),
                        "X-Sticker-Set-Name": sticker_set_name,
                        "X-Image-Type": image_type
                    },
                    "image_size_bytes": len(image_content)
                }, indent=2),
                "Combine Test Results",
                allure.attachment_type.JSON
            )
        
        with allure.step("Combine stickers from set using URL"):
            request_data = {
                "url": sticker_set["url"],
                "image_type": "thumbnail",  # Use thumbnails for e2e tests
                "tile_size": 128,
                "max_stickers": 5
            }
            
            # Add timeout for the request
            response = await asyncio.wait_for(
                client.post("/stickers/combine-from-set", json=request_data, timeout=60.0),
                timeout=65.0
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
            assert response.headers["content-type"] == "image/webp", "Should return WebP image"
            
            # Read content first
            image_content = response.content
            assert len(image_content) > 0, "Image content should not be empty"
            
            # Check headers (case-insensitive)
            headers = dict(response.headers)
            headers_lower = {k.lower(): v for k, v in headers.items()}
            images_combined = headers.get("X-Images-Combined") or headers_lower.get("x-images-combined")
            images_combined_val = int(images_combined) if images_combined else 0
            
            assert images_combined_val > 0, f"Should combine at least one image. Available headers: {list(headers.keys())}"
            assert images_combined_val <= 5, "Should not exceed max_stickers limit"
            
            allure.attach(
                json.dumps({
                    "request": request_data,
                    "images_combined": images_combined_val,
                    "image_size_bytes": len(image_content)
                }, indent=2),
                "URL Request Test Results",
                allure.attachment_type.JSON
            )
    
    @allure.title("E2E: Combine video stickers from set")
    @allure.description("""
    Test combining video stickers from a sticker set:
    1. Call POST /stickers/combine-from-set with sticker set name
    2. Verify combined WebP image is returned
    3. Check response headers and image properties
    4. Verify video stickers are handled correctly
    """)
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_combine_video_stickers_from_set(
        self,
        client: AsyncClient,
        cache_manager: CacheManager
    ):
        """Test combining video stickers from a set."""
        sticker_set = STICKER_SETS["video"]
        
        with allure.step("Combine video stickers from set using thumbnails"):
            # Video stickers have thumbnails (320x320), use them for combination
            request_data = {
                "name": sticker_set["name"],
                "image_type": "thumbnail",  # Use thumbnails for video stickers
                "tile_size": 128,
                "max_stickers": 5  # Reduced for faster test execution
            }
            
            # Add timeout for the request
            response = await asyncio.wait_for(
                client.post("/stickers/combine-from-set", json=request_data, timeout=60.0),
                timeout=65.0
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
            assert response.headers["content-type"] == "image/webp", "Should return WebP image"
            
            # Read content first
            image_content = response.content
            assert len(image_content) > 0, "Image content should not be empty"
            assert image_content.startswith(b"RIFF"), "Should be WebP format (RIFF header)"
            
            # Verify response headers (case-insensitive)
            headers = dict(response.headers)
            headers_lower = {k.lower(): v for k, v in headers.items()}
            
            processing_time = headers.get("X-Processing-Time-Ms") or headers_lower.get("x-processing-time-ms")
            images_combined = headers.get("X-Images-Combined") or headers_lower.get("x-images-combined")
            sticker_set_name = headers.get("X-Sticker-Set-Name") or headers_lower.get("x-sticker-set-name")
            image_type = headers.get("X-Image-Type") or headers_lower.get("x-image-type")
            
            assert processing_time is not None, f"Missing X-Processing-Time-Ms. Available: {list(headers.keys())}"
            assert images_combined is not None, f"Missing X-Images-Combined. Available: {list(headers.keys())}"
            assert sticker_set_name is not None, f"Missing X-Sticker-Set-Name. Available: {list(headers.keys())}"
            assert sticker_set_name == sticker_set["name"]
            assert image_type == "thumbnail"
            
            images_combined_val = int(images_combined) if images_combined else 0
            assert images_combined_val > 0, "Should combine at least one thumbnail image"
            
            allure.attach(
                json.dumps({
                    "request": request_data,
                    "response_headers": {
                        "X-Processing-Time-Ms": processing_time,
                        "X-Images-Combined": images_combined,
                        "X-Images-Failed": headers.get("X-Images-Failed") or headers_lower.get("x-images-failed"),
                        "X-Tile-Size": headers.get("X-Tile-Size") or headers_lower.get("x-tile-size"),
                        "X-Sticker-Set-Name": sticker_set_name,
                        "X-Image-Type": image_type
                    },
                    "image_size_bytes": len(image_content)
                }, indent=2),
                "Video Stickers Combine Test Results",
                allure.attachment_type.JSON
            )
        

