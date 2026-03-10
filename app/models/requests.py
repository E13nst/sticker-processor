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
    model: str = Field(default="dall-e-3", description="OpenAI image generation model (default: 'dall-e-3')")
    quality: str = Field(default="high", description="Image quality: 'high' or 'standard' (default: 'high') - deprecated, not used")
    size: str = Field(default="512x512", description="Image size in format 'WIDTHxHEIGHT' (default: '512x512')")
    
    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v):
        """Validate prompt format."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()
    
    @field_validator('model')
    @classmethod
    def validate_model(cls, v):
        """Validate model name."""
        if not v or not v.strip():
            raise ValueError("Model cannot be empty")
        # Allow any model name, but log common ones
        common_models = ['dall-e-3', 'dall-e-2', 'gpt-image-1']
        if v not in common_models:
            import warnings
            warnings.warn(f"Model '{v}' is not a commonly used OpenAI image model. Using as-is.")
        return v.strip()
    
    @field_validator('quality')
    @classmethod
    def validate_quality(cls, v):
        """Validate quality value (deprecated, kept for backward compatibility)."""
        if v not in ["high", "standard"]:
            raise ValueError("quality must be one of: 'high', 'standard'")
        return v


class WaveSpeedGenerateRequest(BaseModel):
    """Request model for generating sticker image via WaveSpeed."""

    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt for sticker generation")
    model: str = Field(default="flux-schnell", description="WaveSpeed model: 'flux-schnell' or 'nanabanana'")
    size: str = Field(default="512*512", description="Image size in format 'WIDTH*HEIGHT' (default: '512*512')")
    seed: int = Field(default=-1, description="Generation seed (-1 for random)")
    num_images: int = Field(default=1, ge=1, le=1, description="Number of images to generate (currently only 1 is supported)")
    strength: float = Field(default=0.8, ge=0.0, le=1.0, description="Generation strength")
    image: str = Field(default="", description="Deprecated: optional base64 input image for img2img (backward compatibility)")
    source_image_base64: Optional[str] = Field(default=None, description="Optional base64 source image for img2img")
    source_image_url: Optional[str] = Field(default=None, description="Optional source image URL for img2img")
    remove_background: bool = Field(default=False, description="Remove background from generated image")

    @field_validator('prompt')
    @classmethod
    def validate_wavespeed_prompt(cls, v):
        """Validate prompt format."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()

    @field_validator('model')
    @classmethod
    def validate_wavespeed_model(cls, v):
        """Validate WaveSpeed model name."""
        allowed_models = {"flux-schnell", "nanabanana"}
        if not v or not v.strip():
            raise ValueError("Model cannot be empty")

        model = v.strip()
        if model not in allowed_models:
            raise ValueError("model must be one of: 'flux-schnell', 'nanabanana'")
        return model

    @field_validator('size')
    @classmethod
    def validate_wavespeed_size(cls, v):
        """Validate WaveSpeed size format WIDTH*HEIGHT."""
        if not v:
            raise ValueError("Size cannot be empty")

        pattern = r'^\d+\*\d+$'
        if not re.match(pattern, v):
            raise ValueError("Size must be in format 'WIDTH*HEIGHT' (e.g., '512*512')")

        width_str, height_str = v.split('*')
        width = int(width_str)
        height = int(height_str)

        if width < 256 or width > 2048 or height < 256 or height > 2048:
            raise ValueError("Size dimensions must be between 256 and 2048 pixels")

        return v

    @field_validator('source_image_url')
    @classmethod
    def validate_source_image_url(cls, v):
        """Validate source image URL format."""
        if v is None:
            return v
        url = v.strip()
        if not url or url.lower() == "string":
            return None
        if not url.startswith(("http://", "https://")):
            raise ValueError("source_image_url must start with http:// or https://")
        return url

    @field_validator('source_image_base64')
    @classmethod
    def validate_source_image_base64(cls, v):
        """Validate source image base64 field."""
        if v is None:
            return v
        value = v.strip()
        if not value or value.lower() == "string":
            return None
        return value

    @model_validator(mode='after')
    def validate_source_image_fields(self):
        """Normalize source image fields and prevent conflicting inputs."""
        image_value = (self.image or "").strip()
        has_legacy_image = bool(image_value and image_value.lower() != "string")
        has_base64 = bool(self.source_image_base64)
        has_url = bool(self.source_image_url)

        if has_base64 and has_url:
            raise ValueError("Use only one source image field: source_image_base64 or source_image_url")

        # Backward compatibility: if old `image` provided, map it to source_image_base64.
        if has_legacy_image and not has_base64 and not has_url:
            self.source_image_base64 = image_value
        elif has_legacy_image and (has_base64 or has_url):
            raise ValueError("Field 'image' cannot be combined with source_image_base64/source_image_url")

        return self


class SnapstixGenerateRequest(BaseModel):
    """Request model for generating a sticker using Snapstix/RunPod."""
    
    prompt: str = Field(..., min_length=1, max_length=1000, description="Text prompt for sticker generation")
    callback_url: str = Field(..., min_length=1, description="URL to receive callback with generated image")
    processing_id: Optional[str] = Field(default=None, description="Processing job ID (UUID). If not provided, will be generated automatically")
    
    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v):
        """Validate prompt format."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()
    
    @field_validator('callback_url')
    @classmethod
    def validate_callback_url(cls, v):
        """Validate callback URL format."""
        if not v or not v.strip():
            raise ValueError("Callback URL cannot be empty")
        # Basic URL validation
        if not v.startswith(('http://', 'https://')):
            raise ValueError("Callback URL must start with http:// or https://")
        return v.strip()

