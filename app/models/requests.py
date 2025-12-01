"""Request models for incoming API requests."""
from pydantic import BaseModel, Field, validator
from typing import Optional


class FileIdRequest(BaseModel):
    """Request model for file ID operations."""
    
    file_id: str = Field(..., min_length=1, max_length=200, description="Telegram file ID")
    
    @validator('file_id')
    def validate_file_id(cls, v):
        """Validate file ID format."""
        if not v or not v.strip():
            raise ValueError("File ID cannot be empty")
        return v.strip()


class CacheCleanupRequest(BaseModel):
    """Request model for cache cleanup operations."""
    
    force: bool = Field(default=False, description="Force cleanup even if cache is not full")
    target_size_mb: Optional[int] = Field(
        default=None, 
        ge=0, 
        description="Target cache size in MB (optional)"
    )

