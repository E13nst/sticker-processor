"""Request models for incoming API requests."""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
import re


class FileIdRequest(BaseModel):
    """Request model for file ID operations."""
    
    file_id: str = Field(..., min_length=1, max_length=200, description="Telegram file ID")
    
    @field_validator('file_id')
    @classmethod
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
    
    @field_validator('file_ids')
    @classmethod
    def validate_file_ids(cls, v):
        """Validate file IDs format."""
        if not v:
            raise ValueError("File IDs list cannot be empty")
        # Filter out empty strings
        filtered = [fid.strip() for fid in v if fid and fid.strip()]
        if not filtered:
            raise ValueError("File IDs list cannot be empty after filtering")
        return filtered


class CombineStickerSetRequest(BaseModel):
    """Request model for combining stickers from a sticker set into a single image."""
    
    name: Optional[str] = Field(default=None, description="Sticker set name (e.g., 'arcticfox')")
    url: Optional[str] = Field(default=None, description="Sticker set URL (e.g., 'https://t.me/addstickers/arcticfox')")
    image_type: Optional[str] = Field(
        default="main", 
        description="Type of image to use: 'main' (default), 'thumbnail', or 'thumb'"
    )
    tile_size: int = Field(default=128, ge=1, le=2048, description="Size of each tile in pixels (default: 128)")
    max_stickers: Optional[int] = Field(
        default=None,
        ge=1,
        le=1000,
        description="Maximum number of stickers to process (default: no limit). Limits the number of stickers from the set."
    )
    
    @field_validator('image_type')
    @classmethod
    def validate_image_type(cls, v):
        """Validate image type."""
        if v not in ["main", "thumbnail", "thumb"]:
            raise ValueError("image_type must be one of: 'main', 'thumbnail', 'thumb'")
        return v
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        """Validate URL format."""
        if v:
            # Parse URL pattern: https://t.me/addstickers/{name}
            pattern = r'https?://t\.me/addstickers/([^/?]+)'
            match = re.search(pattern, v)
            if not match:
                raise ValueError("Invalid sticker set URL format. Expected: https://t.me/addstickers/{name}")
        return v
    
    @model_validator(mode='after')
    def validate_name_or_url(self):
        """Ensure either name or url is provided, and extract name from URL if needed."""
        # If URL is provided, extract name from it
        if self.url:
            pattern = r'https?://t\.me/addstickers/([^/?]+)'
            match = re.search(pattern, self.url)
            if match:
                extracted_name = match.group(1)
                # If name is also provided, use extracted name from URL (override)
                if self.name and self.name != extracted_name:
                    import warnings
                    warnings.warn(f"Both name ({self.name}) and URL provided. Using name from URL: {extracted_name}")
                self.name = extracted_name
            else:
                raise ValueError("Could not extract sticker set name from URL")
        
        # If no URL, name must be provided
        if not self.name:
            raise ValueError("Either 'name' or 'url' must be provided")
        
        # Strip name if provided
        if self.name:
            self.name = self.name.strip()
        
        return self


class GenerateStickerRequest(BaseModel):
    """Request model for generating a sticker using OpenAI."""
    
    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt for sticker generation")
    quality: str = Field(default="high", description="Image quality: 'high' or 'standard' (default: 'high')")
    size: str = Field(default="512x512", description="Image size in format 'WIDTHxHEIGHT' (default: '512x512')")
    
    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v):
        """Validate prompt format."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()
    
    @field_validator('quality')
    @classmethod
    def validate_quality(cls, v):
        """Validate quality value."""
        if v not in ["high", "standard"]:
            raise ValueError("quality must be one of: 'high', 'standard'")
        return v
    
    @field_validator('size')
    @classmethod
    def validate_size(cls, v):
        """Validate size format."""
        if not v:
            raise ValueError("Size cannot be empty")
        # Validate format: WIDTHxHEIGHT (e.g., "512x512", "1024x1024")
        pattern = r'^\d+x\d+$'
        if not re.match(pattern, v):
            raise ValueError("Size must be in format 'WIDTHxHEIGHT' (e.g., '512x512')")
        # Extract dimensions
        parts = v.split('x')
        width = int(parts[0])
        height = int(parts[1])
        # Validate dimensions are reasonable
        if width < 256 or width > 2048 or height < 256 or height > 2048:
            raise ValueError("Size dimensions must be between 256 and 2048 pixels")
        return v

