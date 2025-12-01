"""
Cache strategy service for intelligent multi-level caching decisions.
"""
import logging
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class CacheStrategy:
    """Intelligent cache strategy service."""
    
    def __init__(self):
        # Configuration for cache strategy
        self.redis_config = {
            'max_size_mb': getattr(settings, 'redis_max_file_size_mb', 5),
            'preferred_formats': getattr(settings, 'redis_preferred_formats', ['lottie', 'webp', 'png', 'jpg']),
            'excluded_formats': getattr(settings, 'redis_excluded_formats', ['tgs']),
        }
        
        self.disk_config = {
            'max_size_mb': getattr(settings, 'disk_max_file_size_mb', 50),
            'all_formats': True,
        }
        
        logger.info(f"Cache strategy initialized:")
        logger.info(f"  Redis: max_size={self.redis_config['max_size_mb']}MB, "
                   f"preferred={self.redis_config['preferred_formats']}, "
                   f"excluded={self.redis_config['excluded_formats']}")
        logger.info(f"  Disk: max_size={self.disk_config['max_size_mb']}MB, all_formats={self.disk_config['all_formats']}")
    
    def should_cache_in_redis(self, file_format: str, file_size: int, is_converted: bool = False) -> bool:
        """
        Determine if file should be cached in Redis.
        
        Args:
            file_format: File format (tgs, lottie, webp, etc.)
            file_size: File size in bytes
            is_converted: Whether file is converted from original format
            
        Returns:
            True if file should be cached in Redis
        """
        # Exclude original formats that are converted
        if file_format in self.redis_config['excluded_formats']:
            return False
            
        # Check file size limit
        max_size_bytes = self.redis_config['max_size_mb'] * 1024 * 1024
        if file_size > max_size_bytes:
            return False
            
        # Prefer converted files and optimized formats
        if is_converted or file_format in self.redis_config['preferred_formats']:
            return True
            
        return False
    
    def should_cache_in_disk(self, file_format: str, file_size: int) -> bool:
        """
        Determine if file should be cached on disk.
        
        Args:
            file_format: File format
            file_size: File size in bytes
            
        Returns:
            True if file should be cached on disk
        """
        # Disk cache accepts all formats by default
        if not self.disk_config['all_formats']:
            return False
            
        # Check file size limit for disk cache
        max_size_bytes = self.disk_config['max_size_mb'] * 1024 * 1024
        if file_size > max_size_bytes:
            return False
            
        return True
    
    def get_cache_levels(self, file_format: str, file_size: int, is_converted: bool = False) -> List[str]:
        """
        Get list of cache levels for a file in order of preference.
        
        Args:
            file_format: File format
            file_size: File size in bytes
            is_converted: Whether file is converted
            
        Returns:
            List of cache levels (e.g., ['redis', 'disk'] or ['disk'])
        """
        levels = []
        
        # Check Redis eligibility
        if self.should_cache_in_redis(file_format, file_size, is_converted):
            levels.append('redis')
            
        # Check disk eligibility
        if self.should_cache_in_disk(file_format, file_size):
            levels.append('disk')
            
        return levels
    
    def get_cache_priority(self, file_format: str, file_size: int, is_converted: bool = False) -> str:
        """
        Get cache priority for a file.
        
        Returns:
            'high', 'medium', or 'low'
        """
        if is_converted and file_size < 1024 * 1024:  # < 1MB converted files
            return 'high'
        elif file_format in self.redis_config['preferred_formats'] and file_size < 5 * 1024 * 1024:  # < 5MB preferred formats
            return 'medium'
        else:
            return 'low'
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """Get current cache strategy configuration."""
        return {
            'redis_config': self.redis_config,
            'disk_config': self.disk_config,
            'strategy_type': 'adaptive'
        }
