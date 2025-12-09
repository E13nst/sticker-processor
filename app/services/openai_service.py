"""OpenAI service for generating sticker images."""
import base64
import logging
from typing import Optional

from openai import OpenAI
from openai import APIError as OpenAIAPIError

from app.config import settings

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI API to generate sticker images."""
    
    def __init__(self):
        """Initialize OpenAI client with API key from settings."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured. Please set it in environment variables.")
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def generate_sticker(
        self,
        prompt: str,
        quality: str = "high",
        size: str = "512x512",
        user: Optional[str] = None
    ) -> bytes:
        """
        Generate a sticker image using OpenAI API.
        
        Args:
            prompt: Text prompt for image generation
            quality: Image quality ("high" or "standard")
            size: Image size in format "WIDTHxHEIGHT" (e.g., "512x512")
            user: Optional user identifier for tracking
            
        Returns:
            bytes: Image data in WebP format
            
        Raises:
            OpenAIAPIError: If OpenAI API call fails
            ValueError: If response data is invalid
        """
        try:
            response = self.client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=size,
                output_format="webp",
                background="transparent",
                quality=quality,
                user=user
            )
            
            if not response.data or len(response.data) == 0:
                raise ValueError("OpenAI API returned empty response")
            
            image_b64 = response.data[0].b64_json
            if not image_b64:
                raise ValueError("OpenAI API response missing b64_json data")
            
            image_bytes = base64.b64decode(image_b64)
            logger.info(f"Successfully generated sticker image: {len(image_bytes)} bytes")
            
            return image_bytes
            
        except OpenAIAPIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating sticker: {e}")
            raise ValueError(f"Failed to generate sticker: {str(e)}") from e

