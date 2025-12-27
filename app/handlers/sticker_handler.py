"""Handler for sticker-related business logic."""
import time
import logging
import asyncio
import io
import aiohttp
from typing import Optional, Tuple, List
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import settings
from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError
from app.services.openai_service import OpenAIService
from app.services.runpod_service import RunPodService
from app.services.image_combiner import (
    image_from_bytes,
    combine_images,
    image_to_webp
)
from app.models.requests import GenerateStickerRequest, SnapstixGenerateRequest
from app.utils.error_handler import handle_telegram_api_error, handle_timeout_error, handle_generic_error
from app.utils.logging_helpers import log_performance
from app.utils.response_builder import build_sticker_response_headers

logger = logging.getLogger(__name__)


class StickerHandler:
    """Handler for sticker operations."""
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize sticker handler with cache manager."""
        self.cache_manager = cache_manager
        self._openai_service = None
        self._runpod_service = None
    
    @property
    def openai_service(self) -> OpenAIService:
        """Lazy initialization of OpenAI service."""
        if self._openai_service is None:
            self._openai_service = OpenAIService()
        return self._openai_service
    
    @property
    def runpod_service(self) -> RunPodService:
        """Lazy initialization of RunPod service."""
        if self._runpod_service is None:
            self._runpod_service = RunPodService()
        return self._runpod_service
    
    async def get_sticker(
        self, 
        file_id: str
    ) -> StreamingResponse:
        """
        Get sticker file by file_id with multi-level caching and adaptive retry.
        
        Args:
            file_id: Telegram file ID
            
        Returns:
            StreamingResponse with sticker content
            
        Raises:
            HTTPException: On errors (404, 429, 500, 504)
        """
        start_time = time.time()
        
        try:
            # Apply overall timeout to prevent gateway timeout (504)
            # Endpoint timeout should be less than gateway timeout (usually 60s)
            try:
                result = await asyncio.wait_for(
                    self.cache_manager.get_sticker(file_id),
                    timeout=settings.endpoint_timeout_sec
                )
            except asyncio.TimeoutError:
                elapsed_time = int((time.time() - start_time) * 1000)
                logger.error(
                    f"Request timeout for sticker {file_id} after {elapsed_time}ms "
                    f"(timeout limit: {settings.endpoint_timeout_sec}s)"
                )
                raise HTTPException(
                    status_code=504,
                    detail=f"Request timeout: processing exceeded {settings.endpoint_timeout_sec} seconds. "
                           f"This may occur when fetching new stickers from Telegram API. "
                           f"Please try again later or check if the file_id is valid."
                )
            
            if not result:
                raise HTTPException(status_code=404, detail="Sticker not found")
            
            content, mime_type, was_converted = result
            processing_time = int((time.time() - start_time) * 1000)
            
            # Prepare response headers
            headers = build_sticker_response_headers(
                file_id, was_converted, len(content), processing_time
            )
            
            # Log performance metrics
            log_performance(file_id, processing_time, was_converted, len(content))
            
            return StreamingResponse(
                io.BytesIO(content),
                media_type=mime_type,
                headers=headers
            )
            
        except asyncio.TimeoutError:
            # Re-raise timeout error (already handled above, but catch here for safety)
            elapsed_time = int((time.time() - start_time) * 1000)
            raise handle_timeout_error(file_id, elapsed_time, settings.endpoint_timeout_sec)
        except TelegramAPIError as te:
            # Return exact Telegram error code and message
            elapsed_time = int((time.time() - start_time) * 1000)
            raise handle_telegram_api_error(te, file_id, elapsed_time)
        except HTTPException:
            raise
        except Exception as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            raise handle_generic_error(e, file_id, elapsed_time)
    
    async def combine_stickers(
        self,
        file_ids: List[str],
        tile_size: int = 128
    ) -> StreamingResponse:
        """
        Combine multiple stickers into a single grid image.
        
        Args:
            file_ids: List of Telegram file IDs to combine
            tile_size: Size of each tile in pixels (default: 128)
            
        Returns:
            StreamingResponse with combined WebP image
            
        Raises:
            HTTPException: On errors (400, 404, 500, 504)
        """
        start_time = time.time()
        
        if not file_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one file_id is required"
            )
        
        try:
            # Fetch all stickers in parallel
            logger.info(f"Fetching {len(file_ids)} stickers for combination")
            
            fetch_tasks = [
                self._fetch_sticker_safe(file_id)
                for file_id in file_ids
            ]
            
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            # Process results: extract successful image downloads
            images = []
            failed_count = 0
            
            for idx, result in enumerate(results):
                file_id = file_ids[idx]
                
                if isinstance(result, Exception):
                    logger.warning(
                        f"Failed to fetch sticker {file_id}: {result}"
                    )
                    failed_count += 1
                    continue
                
                if result is None:
                    logger.warning(f"Sticker {file_id} not found")
                    failed_count += 1
                    continue
                
                content, mime_type, was_converted = result
                
                # Only process image files (skip TGS/Lottie JSON, WebM, etc.)
                if not mime_type.startswith("image/"):
                    logger.warning(
                        f"Skipping {file_id}: not an image (mime_type: {mime_type})"
                    )
                    failed_count += 1
                    continue
                
                try:
                    # Convert bytes to PIL Image
                    image = image_from_bytes(content)
                    images.append(image)
                    logger.debug(f"Successfully loaded image for {file_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to decode image for {file_id}: {e}"
                    )
                    failed_count += 1
                    continue
            
            # Check if we got at least one image
            if not images:
                raise HTTPException(
                    status_code=404,
                    detail=f"Failed to retrieve any images from {len(file_ids)} file_ids. "
                           f"All files either not found, not images, or failed to decode."
                )
            
            if failed_count > 0:
                logger.info(
                    f"Combining {len(images)} images (skipped {failed_count} failed files)"
                )
            
            # Combine images into grid
            try:
                combined_image = combine_images(images, tile_size)
                webp_bytes = image_to_webp(combined_image)
                
                # Сохранить количество изображений для заголовков
                images_count = len(images)
                
                # Освободить память PIL Images после завершения всех операций
                # Удаляем ссылки, но не закрываем явно, чтобы избежать проблем с внутренними ссылками
                del images
                del combined_image
            except Exception as e:
                logger.error(f"Failed to combine images: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to combine images: {str(e)}"
                )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Prepare response headers
            headers = {
                "X-Processing-Time-Ms": str(processing_time),
                "X-Images-Combined": str(images_count),
                "X-Images-Failed": str(failed_count),
                "X-Tile-Size": str(tile_size),
                "Cache-Control": "no-cache"
            }
            
            logger.info(
                f"Successfully combined {images_count} images in {processing_time}ms"
            )
            
            return StreamingResponse(
                io.BytesIO(webp_bytes),
                media_type="image/webp",
                headers=headers
            )
            
        except HTTPException:
            raise
        except Exception as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Error combining stickers: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
    
    async def combine_sticker_set(
        self,
        name: str,
        image_type: str = "main",
        tile_size: int = 128,
        max_stickers: Optional[int] = None
    ) -> StreamingResponse:
        """
        Combine stickers from a sticker set into a single grid image.
        
        Args:
            name: Sticker set name
            image_type: Type of image to use: "main", "thumbnail", or "thumb"
            tile_size: Size of each tile in pixels (default: 128)
            
        Returns:
            StreamingResponse with combined WebP image
            
        Raises:
            HTTPException: On errors (400, 404, 500, 504)
        """
        start_time = time.time()
        
        try:
            # Get sticker set from cache manager (with Redis caching)
            logger.info(f"Fetching sticker set {name} from cache/Telegram API")
            sticker_set = await self.cache_manager.get_sticker_set(name)
            
            if not sticker_set:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sticker set '{name}' not found"
                )
            
            # Extract stickers array
            stickers = sticker_set.get("stickers", [])
            if not stickers:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sticker set '{name}' contains no stickers"
                )
            
            logger.info(f"Found {len(stickers)} stickers in set {name}")
            
            # Apply max_stickers limit if specified
            if max_stickers is not None and max_stickers > 0:
                stickers = stickers[:max_stickers]
                logger.info(f"Limited to first {max_stickers} stickers from set {name}")
            
            # Extract file_ids from stickers in order, based on image_type
            file_ids = []
            skipped_count = 0
            
            for sticker in stickers:
                file_id = None
                
                if image_type == "main":
                    file_id = sticker.get("file_id")
                elif image_type == "thumbnail":
                    thumbnail = sticker.get("thumbnail")
                    if thumbnail:
                        file_id = thumbnail.get("file_id")
                elif image_type == "thumb":
                    thumb = sticker.get("thumb")
                    if thumb:
                        file_id = thumb.get("file_id")
                
                if file_id:
                    file_ids.append(file_id)
                else:
                    skipped_count += 1
                    logger.debug(
                        f"Skipping sticker {sticker.get('emoji', 'unknown')} "
                        f"from set {name}: no {image_type} image available"
                    )
            
            if not file_ids:
                raise HTTPException(
                    status_code=404,
                    detail=f"No {image_type} images found in sticker set '{name}'. "
                           f"All {len(stickers)} stickers were skipped."
                )
            
            if skipped_count > 0:
                logger.info(
                    f"Extracted {len(file_ids)} file_ids from {len(stickers)} stickers "
                    f"(skipped {skipped_count} without {image_type})"
                )
            
            # Fetch all stickers in parallel
            logger.info(f"Fetching {len(file_ids)} images for combination")
            
            fetch_tasks = [
                self._fetch_sticker_safe(file_id)
                for file_id in file_ids
            ]
            
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            # Process results: extract successful image downloads
            images = []
            failed_count = 0
            
            for idx, result in enumerate(results):
                file_id = file_ids[idx]
                
                if isinstance(result, Exception):
                    logger.warning(
                        f"Failed to fetch sticker {file_id}: {result}"
                    )
                    failed_count += 1
                    continue
                
                if result is None:
                    logger.warning(f"Sticker {file_id} not found")
                    failed_count += 1
                    continue
                
                content, mime_type, was_converted = result
                
                # Only process image files (skip TGS/Lottie JSON, WebM, etc.)
                if not mime_type.startswith("image/"):
                    logger.warning(
                        f"Skipping {file_id}: not an image (mime_type: {mime_type})"
                    )
                    failed_count += 1
                    continue
                
                try:
                    # Convert bytes to PIL Image
                    image = image_from_bytes(content)
                    images.append(image)
                    logger.debug(f"Successfully loaded image for {file_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to decode image for {file_id}: {e}"
                    )
                    failed_count += 1
                    continue
            
            # Check if we got at least one image
            if not images:
                raise HTTPException(
                    status_code=404,
                    detail=f"Failed to retrieve any images from sticker set '{name}'. "
                           f"All {len(file_ids)} files either not found, not images, or failed to decode."
                )
            
            if failed_count > 0:
                logger.info(
                    f"Combining {len(images)} images (skipped {failed_count} failed files)"
                )
            
            # Combine images into grid
            try:
                combined_image = combine_images(images, tile_size)
                webp_bytes = image_to_webp(combined_image)
                
                # Сохранить количество изображений для заголовков
                images_count = len(images)
                
                # Освободить память PIL Images после завершения всех операций
                # Удаляем ссылки, но не закрываем явно, чтобы избежать проблем с внутренними ссылками
                del images
                del combined_image
            except Exception as e:
                logger.error(f"Failed to combine images: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to combine images: {str(e)}"
                )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Prepare response headers
            headers = {
                "X-Processing-Time-Ms": str(processing_time),
                "X-Images-Combined": str(images_count),
                "X-Images-Failed": str(failed_count),
                "X-Tile-Size": str(tile_size),
                "X-Sticker-Set-Name": name,
                "X-Image-Type": image_type,
                "Cache-Control": "no-cache"
            }
            
            logger.info(
                f"Successfully combined {images_count} images from sticker set {name} "
                f"in {processing_time}ms"
            )
            
            return StreamingResponse(
                io.BytesIO(webp_bytes),
                media_type="image/webp",
                headers=headers
            )
            
        except HTTPException:
            raise
        except TelegramAPIError as te:
            elapsed_time = int((time.time() - start_time) * 1000)
            raise handle_telegram_api_error(te, name, elapsed_time)
        except RuntimeError as e:
            # Handle "Event loop is closed" errors - common in test environments
            if "Event loop is closed" in str(e):
                elapsed_time = int((time.time() - start_time) * 1000)
                logger.error(f"Event loop closed while combining sticker set {name}: {e}")
                raise HTTPException(
                    status_code=503,
                    detail=f"Service temporarily unavailable: event loop closed. Please retry."
                )
            # Re-raise other RuntimeErrors
            raise
        except Exception as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Error combining sticker set {name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
    
    async def _fetch_sticker_safe(self, file_id: str) -> Optional[Tuple[bytes, str, bool]]:
        """
        Safely fetch a sticker, catching all exceptions.
        
        Args:
            file_id: Telegram file ID
            
        Returns:
            Tuple of (content, mime_type, was_converted) or None if failed
        """
        try:
            result = await asyncio.wait_for(
                self.cache_manager.get_sticker(file_id),
                timeout=settings.endpoint_timeout_sec
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching sticker {file_id}")
            return None
        except TelegramAPIError as te:
            logger.warning(f"Telegram API error for {file_id}: {te}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching sticker {file_id}: {e}")
            return None
    
    async def generate_sticker(
        self,
        request: GenerateStickerRequest
    ) -> StreamingResponse:
        """
        Generate a sticker image using OpenAI API.
        
        Args:
            request: GenerateStickerRequest with prompt, quality, and size
            
        Returns:
            StreamingResponse with WebP image
            
        Raises:
            HTTPException: On errors (400, 500)
        """
        start_time = time.time()
        
        try:
            # Initialize OpenAI service (lazy initialization)
            try:
                openai_service = self.openai_service
            except ValueError as e:
                elapsed_time = int((time.time() - start_time) * 1000)
                logger.error(f"OpenAI service not configured: {e} (time: {elapsed_time}ms)")
                raise HTTPException(
                    status_code=503,
                    detail=f"OpenAI service is not available: {str(e)}. Please configure OPENAI_API_KEY in environment variables."
                )
            
            # Run OpenAI API call in thread pool since it's synchronous
            loop = asyncio.get_event_loop()
            image_bytes = await loop.run_in_executor(
                None,
                openai_service.generate_sticker,
                request.prompt,
                request.model,
                request.quality,
                request.size
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            logger.info(
                f"Generated sticker: prompt='{request.prompt[:50]}...', "
                f"size={len(image_bytes)} bytes, time={processing_time}ms"
            )
            
            return StreamingResponse(
                io.BytesIO(image_bytes),
                media_type="image/webp",
                headers={
                    "X-Processing-Time-Ms": str(processing_time),
                    "X-Image-Size": str(len(image_bytes)),
                    "Content-Type": "image/webp"
                }
            )
            
        except ValueError as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Validation error generating sticker: {e} (time: {elapsed_time}ms)")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to generate sticker: {str(e)}"
            )
        except Exception as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Error generating sticker: {e} (time: {elapsed_time}ms)")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while generating sticker: {str(e)}"
            )
    
    async def generate_snapstix_sticker(
        self,
        request: SnapstixGenerateRequest
    ) -> JSONResponse:
        """
        Generate a sticker using Snapstix/RunPod API.
        
        Args:
            request: SnapstixGenerateRequest with prompt, callback_url, and optional processing_id
            
        Returns:
            JSON response from RunPod API (typically contains job ID and status)
            
        Raises:
            HTTPException: On errors (400, 500, 502, 503, 504)
        """
        start_time = time.time()
        
        try:
            # Get RunPod service
            runpod_service = self.runpod_service
            
            # Call RunPod API (async method)
            response_data = await runpod_service.generate_sticker(
                prompt=request.prompt,
                callback_url=request.callback_url,
                processing_id=request.processing_id
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            logger.info(
                f"Snapstix sticker generation request sent: prompt='{request.prompt[:50]}...', "
                f"processing_id={request.processing_id or 'generated'}, time={processing_time}ms"
            )
            
            # Return JSON response from RunPod API
            return JSONResponse(
                content=response_data,
                headers={
                    "X-Processing-Time-Ms": str(processing_time),
                    "Content-Type": "application/json"
                }
            )
            
        except ValueError as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Validation error generating Snapstix sticker: {e} (time: {elapsed_time}ms)")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to generate sticker: {str(e)}"
            )
        except aiohttp.ClientResponseError as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"RunPod API error generating Snapstix sticker: {e} (time: {elapsed_time}ms)")
            # Map HTTP errors appropriately
            if e.status >= 500:
                raise HTTPException(
                    status_code=502,
                    detail=f"RunPod API server error: {str(e)}"
                )
            elif e.status == 429:
                raise HTTPException(
                    status_code=503,
                    detail=f"RunPod API rate limited: {str(e)}"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"RunPod API client error: {str(e)}"
                )
        except asyncio.TimeoutError:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Timeout generating Snapstix sticker (time: {elapsed_time}ms)")
            raise HTTPException(
                status_code=504,
                detail="Request to RunPod API timed out. Please try again later."
            )
        except Exception as e:
            elapsed_time = int((time.time() - start_time) * 1000)
            logger.error(f"Error generating Snapstix sticker: {e} (time: {elapsed_time}ms)")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while generating sticker: {str(e)}"
            )

