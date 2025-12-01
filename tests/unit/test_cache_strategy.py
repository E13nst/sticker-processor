"""Unit tests for cache strategy service."""
import pytest
import allure
from app.services.cache_strategy import CacheStrategy


@allure.feature("Cache Strategy")
@allure.tag("cache", "strategy", "unit")
@pytest.mark.unit
class TestCacheStrategy:
    """Test CacheStrategy functionality."""
    
    @allure.title("Cache strategy initialization")
    @allure.description("Test that cache strategy initializes with correct configuration")
    @allure.severity(allure.severity_level.NORMAL)
    def test_cache_strategy_initialization(self, cache_strategy):
        """Test cache strategy initializes correctly."""
        with allure.step("Check cache strategy instance"):
            assert cache_strategy is not None
            assert hasattr(cache_strategy, 'redis_config')
            assert hasattr(cache_strategy, 'disk_config')
        
        with allure.step("Verify Redis configuration"):
            assert 'max_size_mb' in cache_strategy.redis_config
            assert 'preferred_formats' in cache_strategy.redis_config
            assert 'excluded_formats' in cache_strategy.redis_config
        
        with allure.step("Verify disk configuration"):
            assert 'max_size_mb' in cache_strategy.disk_config
            assert 'all_formats' in cache_strategy.disk_config
    
    @allure.title("Redis cache decision - should cache converted lottie")
    @allure.description("Test that converted lottie files should be cached in Redis")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_cache_in_redis_lottie(self, cache_strategy):
        """Test that lottie files should be cached in Redis."""
        with allure.step("Check small converted lottie file"):
            result = cache_strategy.should_cache_in_redis('lottie', 100 * 1024, is_converted=True)
            assert result is True
        
        with allure.step("Check medium converted lottie file"):
            result = cache_strategy.should_cache_in_redis('lottie', 2 * 1024 * 1024, is_converted=True)
            assert result is True
    
    @allure.title("Redis cache decision - should not cache TGS")
    @allure.description("Test that TGS files should not be cached in Redis (excluded format)")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_not_cache_tgs_in_redis(self, cache_strategy):
        """Test that TGS files should not be cached in Redis."""
        with allure.step("Check TGS file is excluded"):
            result = cache_strategy.should_cache_in_redis('tgs', 100 * 1024, is_converted=False)
            assert result is False
    
    @allure.title("Redis cache decision - file size limit")
    @allure.description("Test that large files should not be cached in Redis")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_not_cache_large_files_in_redis(self, cache_strategy):
        """Test that files exceeding size limit should not be cached in Redis."""
        max_size_mb = cache_strategy.redis_config['max_size_mb']
        large_size = (max_size_mb + 1) * 1024 * 1024
        
        with allure.step(f"Check file larger than {max_size_mb}MB is rejected"):
            result = cache_strategy.should_cache_in_redis('lottie', large_size, is_converted=True)
            assert result is False
    
    @allure.title("Redis cache decision - preferred formats")
    @allure.description("Test that preferred formats should be cached in Redis")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_cache_preferred_formats(self, cache_strategy):
        """Test that preferred formats should be cached in Redis."""
        preferred_formats = cache_strategy.redis_config['preferred_formats']
        
        for format_name in preferred_formats:
            with allure.step(f"Check {format_name} format is cached"):
                result = cache_strategy.should_cache_in_redis(format_name, 100 * 1024, is_converted=False)
                assert result is True
    
    @allure.title("Disk cache decision - should cache all formats")
    @allure.description("Test that disk cache accepts all formats within size limit")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_cache_in_disk(self, cache_strategy):
        """Test that files should be cached on disk."""
        with allure.step("Check small file is cached"):
            result = cache_strategy.should_cache_in_disk('lottie', 100 * 1024)
            assert result is True
        
        with allure.step("Check TGS file is cached"):
            result = cache_strategy.should_cache_in_disk('tgs', 100 * 1024)
            assert result is True
        
        with allure.step("Check webp file is cached"):
            result = cache_strategy.should_cache_in_disk('webp', 500 * 1024)
            assert result is True
    
    @allure.title("Disk cache decision - file size limit")
    @allure.description("Test that large files should not be cached on disk")
    @allure.severity(allure.severity_level.NORMAL)
    def test_should_not_cache_large_files_in_disk(self, cache_strategy):
        """Test that files exceeding disk size limit should not be cached."""
        max_size_mb = cache_strategy.disk_config['max_size_mb']
        large_size = (max_size_mb + 1) * 1024 * 1024
        
        with allure.step(f"Check file larger than {max_size_mb}MB is rejected"):
            result = cache_strategy.should_cache_in_disk('lottie', large_size)
            assert result is False
    
    @allure.title("Get cache levels - multi-level caching")
    @allure.description("Test that cache levels are determined correctly")
    @allure.severity(allure.severity_level.NORMAL)
    def test_get_cache_levels(self, cache_strategy):
        """Test getting cache levels for a file."""
        with allure.step("Check converted lottie gets both levels"):
            levels = cache_strategy.get_cache_levels('lottie', 100 * 1024, is_converted=True)
            assert 'redis' in levels
            assert 'disk' in levels
        
        with allure.step("Check TGS gets only disk level"):
            levels = cache_strategy.get_cache_levels('tgs', 100 * 1024, is_converted=False)
            assert 'redis' not in levels
            assert 'disk' in levels
    
    @allure.title("Get cache priority - priority levels")
    @allure.description("Test that cache priority is determined correctly")
    @allure.severity(allure.severity_level.NORMAL)
    def test_get_cache_priority(self, cache_strategy):
        """Test getting cache priority for a file."""
        with allure.step("Check small converted file gets high priority"):
            priority = cache_strategy.get_cache_priority('lottie', 500 * 1024, is_converted=True)
            assert priority == 'high'
        
        with allure.step("Check medium preferred format gets medium priority"):
            priority = cache_strategy.get_cache_priority('webp', 2 * 1024 * 1024, is_converted=False)
            assert priority == 'medium'
        
        with allure.step("Check large file gets low priority"):
            priority = cache_strategy.get_cache_priority('webp', 10 * 1024 * 1024, is_converted=False)
            assert priority == 'low'
    
    @allure.title("Get strategy stats")
    @allure.description("Test that strategy statistics are returned correctly")
    @allure.severity(allure.severity_level.MINOR)
    def test_get_strategy_stats(self, cache_strategy):
        """Test getting strategy statistics."""
        with allure.step("Get strategy stats"):
            stats = cache_strategy.get_strategy_stats()
            assert stats is not None
            assert 'redis_config' in stats
            assert 'disk_config' in stats
            assert 'strategy_type' in stats
            assert stats['strategy_type'] == 'adaptive'

