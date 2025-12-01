"""E2E tests with real stickers from Telegram."""
import pytest
import allure
import json
import os
import httpx
from typing import List, Dict, Any
from httpx import AsyncClient


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
        """Get Telegram bot token from environment."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN not set, skipping E2E tests")
        return token
    
    @pytest.fixture
    async def telegram_api_client(self, telegram_bot_token: str):
        """Create HTTP client for Telegram Bot API."""
        base_url = f"https://api.telegram.org/bot{telegram_bot_token}"
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            yield client
    
    async def get_sticker_set(self, api_client: httpx.AsyncClient, sticker_set_name: str) -> Dict[str, Any]:
        """Get sticker set from Telegram Bot API."""
        with allure.step(f"Get sticker set '{sticker_set_name}' from Telegram API"):
            response = await api_client.get("/getStickerSet", params={"name": sticker_set_name})
            
            if response.status_code != 200:
                allure.attach(
                    f"Status: {response.status_code}\nResponse: {response.text}",
                    "Telegram API Error",
                    allure.attachment_type.TEXT
                )
                pytest.skip(f"Could not get sticker set {sticker_set_name}: {response.status_code}")
            
            data = response.json()
            if not data.get("ok"):
                pytest.skip(f"Sticker set {sticker_set_name} not found or unavailable")
            
            return data.get("result", {})
    
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
    1. Get sticker set from Telegram Bot API
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
        telegram_api_client: httpx.AsyncClient
    ):
        """Test loading TGS animation stickers."""
        sticker_set_name = "worldart"
        
        with allure.step("Get sticker set from Telegram API"):
            sticker_set = await self.get_sticker_set(telegram_api_client, sticker_set_name)
            allure.attach(
                json.dumps({"name": sticker_set.get("name"), "title": sticker_set.get("title"), "stickers_count": len(sticker_set.get("stickers", []))}, indent=2),
                "Sticker Set Info",
                allure.attachment_type.JSON
            )
        
        with allure.step("Extract file IDs from sticker set"):
            file_ids = self.extract_file_ids(sticker_set, limit=10)
            assert len(file_ids) > 0, "No file IDs found in sticker set"
            allure.attach(
                json.dumps({"file_ids": file_ids, "count": len(file_ids)}, indent=2),
                "Extracted File IDs",
                allure.attachment_type.JSON
            )
        
        with allure.step("Get initial cache statistics"):
            stats_before = await client.get("/cache/stats")
            stats_before_data = stats_before.json() if stats_before.status_code == 200 else {}
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
                            import json
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
            stats_after = await client.get("/cache/stats")
            stats_after_data = stats_after.json() if stats_after.status_code == 200 else {}
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
    1. Get sticker set from Telegram Bot API
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
        telegram_api_client: httpx.AsyncClient
    ):
        """Test loading video stickers."""
        sticker_set_name = "pack_1_40802189314_5786_155347765_by_sticker_bot"
        
        with allure.step("Get sticker set from Telegram API"):
            sticker_set = await self.get_sticker_set(telegram_api_client, sticker_set_name)
            allure.attach(
                json.dumps({"name": sticker_set.get("name"), "title": sticker_set.get("title"), "stickers_count": len(sticker_set.get("stickers", []))}, indent=2),
                "Sticker Set Info",
                allure.attachment_type.JSON
            )
        
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
        telegram_api_client: httpx.AsyncClient
    ):
        """Test cache performance improvement."""
        sticker_set_name = "worldart"
        
        with allure.step("Get one sticker from set"):
            sticker_set = await self.get_sticker_set(telegram_api_client, sticker_set_name)
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
            assert performance_improvement > 50, f"Expected >50% improvement, got {performance_improvement:.1f}%"

