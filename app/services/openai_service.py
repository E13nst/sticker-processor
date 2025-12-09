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
    
    def _generate_with_model(
        self,
        model: str,
        prompt: str,
        size: str,
        user: Optional[str] = None,
        background_transparent: bool = False
    ) -> bytes:
        """
        Internal method to generate image with specific model.
        
        Args:
            model: Model name ("gpt-image-1" or "dall-e-3")
            prompt: Text prompt
            size: Image size
            user: Optional user identifier
            background_transparent: Whether to request transparent background
            
        Returns:
            bytes: Image data
        """
        request_params = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1
        }
        
        # Model-specific parameters
        if model == "dall-e-3":
            # DALL-E 3 supports response_format and background
            request_params["response_format"] = "b64_json"
            if background_transparent:
                request_params["background"] = "transparent"
        elif model == "gpt-image-1":
            # gpt-image-1 doesn't support response_format or background
            pass
        
        # Add optional user parameter
        if user:
            request_params["user"] = user
        
        logger.info(
            f"OpenAI API request - calling images.generate() with model={model}, "
            f"prompt='{prompt[:100]}{'...' if len(prompt) > 100 else ''}', "
            f"size={size}, params={request_params}"
        )
        
        response = self.client.images.generate(**request_params)
        
        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI API returned empty response")
        
        image_data = response.data[0]
        
        # Get image bytes
        if hasattr(image_data, 'b64_json') and image_data.b64_json:
            image_bytes = base64.b64decode(image_data.b64_json)
        elif hasattr(image_data, 'url') and image_data.url:
            logger.info(f"Downloading image from URL: {image_data.url}")
            img_response = requests.get(image_data.url, timeout=30)
            img_response.raise_for_status()
            image_bytes = img_response.content
        else:
            raise ValueError(
                f"OpenAI API response format not recognized. "
                f"Available attributes: {dir(image_data)}"
            )
        
        return image_bytes
    
    def generate_sticker(
        self,
        prompt: str,
        quality: str = "high",
        size: str = "512x512",
        user: Optional[str] = None
    ) -> bytes:
        """
        Generate a sticker image using OpenAI API with fallback support.
        
        Args:
            prompt: Text prompt for image generation
            quality: Image quality ("high" or "standard") - not used by API
            size: Image size in format "WIDTHxHEIGHT" (e.g., "512x512")
            user: Optional user identifier for tracking
            
        Returns:
            bytes: Image data in WebP format
            
        Raises:
            OpenAIAPIError: If OpenAI API call fails
            ValueError: If response data is invalid
        """
        requested_size = size
        api_size = size
        needs_scaling = False
        target_width = None
        target_height = None
        
        # Determine target size and scaling needs
        if size == "512x512":
            # For 512x512, always generate at 1024x1024 and scale down
            api_size = "1024x1024"
            needs_scaling = True
            target_width = 512
            target_height = 512
            logger.info(
                f"Size 512x512 requested - will generate at 1024x1024 and scale down to 512x512"
            )
        
        # Try primary model first, then fallback
        primary_model = getattr(settings, 'openai_image_model', 'gpt-image-1')
        fallback_model = getattr(settings, 'openai_fallback_model', 'dall-e-3')
        
        models_to_try = [primary_model]
        if fallback_model != primary_model:
            models_to_try.append(fallback_model)
        
        last_error = None
        
        for model in models_to_try:
            try:
                logger.info(f"Attempting to generate image with model: {model}")
                
                # DALL-E 3 supports transparent background
                background_transparent = (model == "dall-e-3")
                
                image_bytes = self._generate_with_model(
                    model=model,
                    prompt=prompt,
                    size=api_size,
                    user=user,
                    background_transparent=background_transparent
                )
                
                logger.info(
                    f"Successfully generated image with {model}: "
                    f"size={len(image_bytes)} bytes"
                )
                
                # Scale down if needed
                if needs_scaling and target_width and target_height:
                    logger.info(
                        f"Scaling image from {api_size} to {target_width}x{target_height}"
                    )
                    try:
                        img = Image.open(BytesIO(image_bytes))
                        
                        # Convert to RGBA for transparency support
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
                last_error = e
                error_code = getattr(e, 'status_code', None)
                error_message = str(e)
                
                # Check if it's a 403 (organization not verified) or other retryable error
                if error_code == 403 and "verified" in error_message.lower():
                    logger.warning(
                        f"Model {model} requires organization verification (403). "
                        f"Error: {error_message}. Trying fallback model..."
                    )
                    if model == models_to_try[-1]:
                        # Last model, re-raise
                        raise
                    continue
                else:
                    # Other API errors - log and re-raise
                    logger.error(
                        f"OpenAI API error with model {model}: {type(e).__name__}: {e}"
                    )
                    if model == models_to_try[-1]:
                        raise
                    continue
                    
            except Exception as e:
                last_error = e
                logger.error(
                    f"Error generating image with model {model}: {type(e).__name__}: {e}"
                )
                if model == models_to_try[-1]:
                    raise ValueError(f"Failed to generate sticker: {str(e)}") from e
                continue
        
        # If we get here, all models failed
        if last_error:
            raise ValueError(f"Failed to generate sticker with all models: {str(last_error)}") from last_error
        else:
            raise ValueError("Failed to generate sticker: unknown error")
            
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
        
        # If we get here, all models failed
        if last_error:
            raise ValueError(f"Failed to generate sticker with all models: {str(last_error)}") from last_error
        else:
            raise ValueError("Failed to generate sticker: unknown error")

