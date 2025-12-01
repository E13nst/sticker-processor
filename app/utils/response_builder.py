"""Response building utilities."""
from typing import Dict
from app.config import settings


def build_sticker_response_headers(
    file_id: str,
    was_converted: bool,
    content_size: int,
    processing_time_ms: int
) -> Dict[str, str]:
    """
    Build response headers for sticker endpoint.
    
    Args:
        file_id: Telegram file ID
        was_converted: Whether file was converted
        content_size: Content size in bytes
        processing_time_ms: Processing time in milliseconds
        
    Returns:
        Dictionary of response headers
    """
    return {
        "X-File-ID": file_id,
        "X-Is-Converted": str(was_converted),
        "X-File-Size": str(content_size),
        "X-Processing-Time-Ms": str(processing_time_ms),
        "Cache-Control": f"max-age={settings.cache_ttl_days * 24 * 60 * 60}, public"
    }

