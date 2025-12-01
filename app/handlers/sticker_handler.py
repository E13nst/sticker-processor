"""Handler for sticker-related business logic."""
import time
import logging
import asyncio
import io
from typing import Optional, Tuple, List
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError
from app.services.image_combiner import (
    image_from_bytes,
    combine_images,
    image_to_webp
)
from app.utils.error_handler import handle_telegram_api_error, handle_timeout_error, handle_generic_error
from app.utils.logging_helpers import log_performance
from app.utils.response_builder import build_sticker_response_headers

logger = logging.getLogger(__name__)


class StickerHandler:
    """Handler for sticker operations."""
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize sticker handler with cache manager."""
        self.cache_manager = cache_manager
    
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
                "X-Images-Combined": str(len(images)),
                "X-Images-Failed": str(failed_count),
                "X-Tile-Size": str(tile_size),
                "Cache-Control": "no-cache"
            }
            
            logger.info(
                f"Successfully combined {len(images)} images in {processing_time}ms"
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
                "X-Images-Combined": str(len(images)),
                "X-Images-Failed": str(failed_count),
                "X-Tile-Size": str(tile_size),
                "X-Sticker-Set-Name": name,
                "X-Image-Type": image_type,
                "Cache-Control": "no-cache"
            }
            
            logger.info(
                f"Successfully combined {len(images)} images from sticker set {name} "
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

