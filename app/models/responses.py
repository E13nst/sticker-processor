from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class StickerCache(BaseModel):
    """Model for cached sticker data."""
    
    file_id: str
    file_data: bytes
    mime_type: str
    file_name: str
    file_size: int
    original_format: str
    output_format: str
    telegram_file_path: Optional[str] = None
    last_updated: datetime
    conversion_time_ms: Optional[int] = None
    is_converted: bool = False


class StickerResponse(BaseModel):
    """Response model for sticker endpoint."""
    
    file_id: str
    original_format: str
    output_format: str
    file_size: int
    conversion_time_ms: Optional[int] = None
    cache_status: str
    mime_type: str


class CacheStats(BaseModel):
    """Model for cache statistics."""
    
    total_files: int
    total_size_bytes: int
    converted_files: int
    original_files: int
    last_updated: datetime
    file_types: Optional[Dict[str, int]] = None  # Statistics by file type


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str
    message: str
    file_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
