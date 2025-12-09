"""OpenAI service for generating sticker images."""
import base64
import logging
from io import BytesIO
from typing import Optional

import requests
from PIL import Image
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
        try:
            # Initialize client with only api_key to avoid issues with proxies parameter
            # httpx 0.28+ removed proxies parameter, so we explicitly pass only api_key
            self.client = OpenAI(api_key=settings.openai_api_key)
        except TypeError as e:
            if "proxies" in str(e):
                logger.error(
                    "OpenAI client initialization failed due to proxies parameter. "
                    "This may be caused by incompatible httpx version. "
                    "Please ensure httpx==0.27.2 is installed."
                )
            raise ValueError(f"Failed to initialize OpenAI client: {str(e)}") from e
    
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
        request_params = {}
        try:
            # Prepare request parameters for gpt-image-1 model
            # Note: gpt-image-1 doesn't support response_format or quality parameters
            # Supported sizes: '1024x1024', '1024x1536', '1536x1024', 'auto'
            # If 512x512 is requested, we'll generate 1024x1024 and scale down
            requested_size = size
            api_size = size
            needs_scaling = False
            target_width = None
            target_height = None
            
            if size == "512x512":
                # Generate at 1024x1024 and scale down to 512x512
                api_size = "1024x1024"
                needs_scaling = True
                target_width = 512
                target_height = 512
                logger.info(
                    f"Size 512x512 requested - will generate at 1024x1024 and scale down to 512x512"
                )
            
            request_params["model"] = "gpt-image-1"
            request_params["prompt"] = prompt
            request_params["size"] = api_size
            request_params["n"] = 1
            
            # Add optional parameters
            if user:
                request_params["user"] = user
            
            # Log the exact request being sent to OpenAI
            logger.info(
                f"OpenAI API request - calling images.generate() with parameters: "
                f"model={request_params.get('model')}, "
                f"prompt='{prompt[:100]}{'...' if len(prompt) > 100 else ''}', "
                f"requested_size={requested_size}, api_size={api_size}, "
                f"needs_scaling={needs_scaling}, "
                f"n={request_params.get('n')}, "
                f"user={user if user else 'None'}, "
                f"all_params={request_params}"
            )
            
            # Call OpenAI API with the prepared parameters
            response = self.client.images.generate(**request_params)
            
            logger.debug(
                f"OpenAI API response received: "
                f"status=success, images_count={len(response.data) if response.data else 0}, "
                f"response_type={type(response.data[0]) if response.data else 'None'}"
            )
            
            if not response.data or len(response.data) == 0:
                raise ValueError("OpenAI API returned empty response")
            
            # gpt-image-1 returns image data - check if it's URL or base64
            image_data = response.data[0]
            
            # Check if response has b64_json (base64 encoded)
            if hasattr(image_data, 'b64_json') and image_data.b64_json:
                image_bytes = base64.b64decode(image_data.b64_json)
                logger.info(
                    f"Successfully generated sticker image from base64: "
                    f"size={len(image_bytes)} bytes"
                )
            # Check if response has url (need to download)
            elif hasattr(image_data, 'url') and image_data.url:
                logger.info(f"Downloading image from URL: {image_data.url}")
                # Download image synchronously (since this method is sync)
                img_response = requests.get(image_data.url, timeout=30)
                img_response.raise_for_status()
                image_bytes = img_response.content
                logger.info(
                    f"Successfully downloaded sticker image: "
                    f"size={len(image_bytes)} bytes, "
                    f"content_type={img_response.headers.get('content-type', 'unknown')}"
                )
            else:
                # Try to get raw data if available
                raise ValueError(
                    f"OpenAI API response format not recognized. "
                    f"Available attributes: {dir(image_data)}"
                )
            
            # Scale down image if needed (e.g., 512x512 from 1024x1024)
            if needs_scaling and target_width and target_height:
                logger.info(
                    f"Scaling image from {api_size} to {target_width}x{target_height}"
                )
                try:
                    # Open image from bytes
                    img = Image.open(BytesIO(image_bytes))
                    
                    # Convert to RGBA if needed (for transparency support)
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    
                    # Resize using high-quality Lanczos resampling
                    img_resized = img.resize(
                        (target_width, target_height),
                        Image.Resampling.LANCZOS
                    )
                    
                    # Save back to WebP format with transparency
                    output = BytesIO()
                    img_resized.save(
                        output,
                        format='WEBP',
                        method=6,  # Best quality
                        lossless=False
                    )
                    image_bytes = output.getvalue()
                    
                    logger.info(
                        f"Successfully scaled image: "
                        f"original={api_size}, scaled={target_width}x{target_height}, "
                        f"final_size={len(image_bytes)} bytes"
                    )
                except Exception as e:
                    logger.error(f"Error scaling image: {e}")
                    raise ValueError(f"Failed to scale image: {str(e)}") from e
            
            return image_bytes
            
        except OpenAIAPIError as e:
            logger.error(
                f"OpenAI API error: {type(e).__name__}: {e}, "
                f"request_params={request_params}"
            )
            raise
        except TypeError as e:
            logger.error(
                f"OpenAI API TypeError: {type(e).__name__}: {e}, "
                f"request_params={request_params}, "
                f"this usually means an unsupported parameter was passed"
            )
            raise ValueError(f"Invalid API parameters: {str(e)}") from e
        except Exception as e:
            logger.error(
                f"Error generating sticker: {type(e).__name__}: {e}, "
                f"request_params={request_params}"
            )
            raise ValueError(f"Failed to generate sticker: {str(e)}") from e

