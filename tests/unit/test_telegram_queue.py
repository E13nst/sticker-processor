"""Unit tests for Telegram request queue."""
import pytest
import allure
import asyncio
from app.services.telegram_queue import TelegramRequestQueue


@allure.feature("Telegram Queue")
@allure.tag("telegram", "queue", "rate-limiting", "unit")
@pytest.mark.unit
class TestTelegramRequestQueue:
    """Test TelegramRequestQueue functionality."""
    
    @allure.title("Queue initialization")
    @allure.description("Test that queue initializes with correct parameters")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_queue_initialization(self, telegram_queue):
        """Test queue initializes correctly."""
        with allure.step("Check queue instance"):
            assert telegram_queue is not None
            assert telegram_queue.max_concurrent == 2
            assert telegram_queue.base_delay == 0.05  # 50ms
        
        with allure.step("Verify queue state"):
            assert telegram_queue.adaptive is True
            assert telegram_queue.rate_limit_active is False
    
    @allure.title("Execute request through queue")
    @allure.description("Test executing async function through queue")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_execute_request(self, telegram_queue):
        """Test executing request through queue."""
        async def test_func(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2
        
        with allure.step("Execute function through queue"):
            result = await telegram_queue.execute(test_func, 5)
            assert result == 10
    
    @allure.title("Concurrent request limiting")
    @allure.description("Test that concurrent requests are limited by semaphore")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_concurrent_limiting(self, telegram_queue):
        """Test concurrent request limiting."""
        call_count = [0]
        
        async def test_func():
            call_count[0] += 1
            await asyncio.sleep(0.05)
            return call_count[0]
        
        with allure.step("Execute multiple concurrent requests"):
            tasks = [telegram_queue.execute(test_func) for _ in range(5)]
            results = await asyncio.gather(*tasks)
        
        with allure.step("Verify results"):
            assert len(results) == 5
            assert all(r > 0 for r in results)
    
    @allure.title("Rate limit handling")
    @allure.description("Test handling of 429 rate limit errors")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, telegram_queue):
        """Test handling rate limit errors."""
        class RateLimitError(Exception):
            def __init__(self):
                self.status = 429
                super().__init__("Rate limit exceeded")
        
        async def failing_func():
            raise RateLimitError()
        
        with allure.step("Execute function that raises 429 error"):
            with pytest.raises(RateLimitError):
                await telegram_queue.execute(failing_func)
        
        with allure.step("Verify rate limit state updated"):
            assert telegram_queue.consecutive_429_count > 0
            assert telegram_queue.current_delay > telegram_queue.base_delay
    
    @allure.title("Adaptive delay adjustment")
    @allure.description("Test that delay adjusts based on success/failure")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.asyncio
    async def test_adaptive_delay(self, telegram_queue):
        """Test adaptive delay adjustment."""
        initial_delay = telegram_queue.current_delay
        
        async def success_func():
            return "success"
        
        with allure.step("Execute successful requests"):
            for _ in range(5):
                await telegram_queue.execute(success_func)
        
        with allure.step("Verify delay may adjust (but not below base)"):
            assert telegram_queue.current_delay >= telegram_queue.base_delay
    
    @allure.title("Queue shutdown")
    @allure.description("Test graceful shutdown of queue processor")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.asyncio
    async def test_queue_shutdown(self, telegram_queue):
        """Test queue shutdown."""
        with allure.step("Start queue processor"):
            telegram_queue._start_processor()
            assert telegram_queue._running is True
        
        with allure.step("Shutdown queue"):
            await telegram_queue.shutdown()
            # Give it a moment to shutdown
            await asyncio.sleep(0.1)
        
        with allure.step("Verify queue is stopped"):
            assert telegram_queue._running is False

