"""Logging helper utilities."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_performance(
    file_id: str,
    processing_time_ms: int,
    was_converted: bool,
    content_size: int,
    slow_threshold_ms: int = 5000
) -> None:
    """
    Log performance metrics for requests.
    
    Args:
        file_id: File ID for logging
        processing_time_ms: Processing time in milliseconds
        was_converted: Whether file was converted
        content_size: Content size in bytes
        slow_threshold_ms: Threshold for slow requests (default: 5000ms)
    """
    if processing_time_ms > slow_threshold_ms:
        logger.warning(
            f"Slow request for sticker {file_id}: {processing_time_ms}ms "
            f"(converted: {was_converted}, size: {content_size} bytes)"
        )
    else:
        logger.info(
            f"Serving sticker {file_id} (converted: {was_converted}, "
            f"size: {content_size} bytes, time: {processing_time_ms}ms)"
        )


def log_cache_hit(
    cache_level: str,
    file_id: str,
    format_name: str,
    size_bytes: int,
    cache_time_ms: int,
    total_time_ms: int
) -> None:
    """
    Log cache hit information.
    
    Args:
        cache_level: Cache level (e.g., "Redis", "Disk")
        file_id: File ID
        format_name: File format
        size_bytes: File size in bytes
        cache_time_ms: Cache lookup time in milliseconds
        total_time_ms: Total request time in milliseconds
    """
    logger.info(
        f"📦 CACHE: {cache_level} HIT - file_id={file_id}, format={format_name}, "
        f"size={size_bytes} bytes, cache_time={cache_time_ms}ms, "
        f"total_time={total_time_ms}ms"
    )


def log_cache_miss(
    file_id: str,
    cache_check_time_ms: int
) -> None:
    """
    Log cache miss information.
    
    Args:
        file_id: File ID
        cache_check_time_ms: Time spent checking cache in milliseconds
    """
    logger.info(
        f"📥 CACHE: MISS - no cache hit, will fetch from Telegram API, "
        f"file_id={file_id}, cache_check_time={cache_check_time_ms}ms"
    )

