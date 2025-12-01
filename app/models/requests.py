"""Request models for incoming API requests."""
from pydantic import BaseModel, Field, validator
from typing import Optional, List


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


class CombineStickersRequest(BaseModel):
    """Request model for combining multiple stickers into a single image."""
    
    file_ids: List[str] = Field(..., min_items=1, description="List of Telegram file IDs to combine")
    tile_size: int = Field(default=128, ge=1, le=2048, description="Size of each tile in pixels (default: 128)")
    
    @validator('file_ids')
    def validate_file_ids(cls, v):
        """Validate file IDs format."""
        if not v:
            raise ValueError("File IDs list cannot be empty")
        # Filter out empty strings
        filtered = [fid.strip() for fid in v if fid and fid.strip()]
        if not filtered:
            raise ValueError("File IDs list cannot be empty after filtering")
        return filtered

