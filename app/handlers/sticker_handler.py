"""Handler for sticker-related business logic."""
import time
import logging
import asyncio
import io
import aiohttp
import hashlib
import base64
import json
from datetime import datetime
from typing import Optional, Tuple, List
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import settings
from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError
from app.services.openai_service import OpenAIService
from app.services.runpod_service import RunPodService
from app.services.sticker_normalizer import StickerNormalizer
from app.services.wavespeed_generation_service import WaveSpeedGenerationService
from app.services.wavespeed_registry import WaveSpeedRegistryService
from app.services.image_combiner import (
    image_from_bytes,
    combine_images,
    image_to_webp
)
from app.models.requests import (
    GenerateStickerRequest,
    SnapstixGenerateRequest,
    WaveSpeedGenerateRequest,
    WaveSpeedSaveToSetRequest,
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
        self._openai_service = None
        self._runpod_service = None
        self._wavespeed_service = None
        self._wavespeed_registry = None
        self._sticker_normalizer = StickerNormalizer()
        self._ws_materialize_semaphore = asyncio.Semaphore(settings.wavespeed_max_materialize_concurrency)
        self._ws_locks = {}
        self._ws_save_to_set_idempotency_cache = {}
    
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

    @property
    def wavespeed_service(self) -> WaveSpeedGenerationService:
        """Lazy initialization of WaveSpeed service."""
        if self._wavespeed_service is None:
            self._wavespeed_service = WaveSpeedGenerationService()
        return self._wavespeed_service

    @property
    def wavespeed_registry(self) -> WaveSpeedRegistryService:
        """Lazy initialization of WaveSpeed metadata registry."""
        if self._wavespeed_registry is None:
            self._wavespeed_registry = WaveSpeedRegistryService()
        return self._wavespeed_registry
    
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

    async def generate_wavespeed_sticker(
        self,
        request: WaveSpeedGenerateRequest
    ) -> JSONResponse:
        """Submit WaveSpeed generation job and return synthetic file_id."""
        start_time = time.time()

        try:
            wavespeed_service = self.wavespeed_service
            registry = self.wavespeed_registry
            source_images = await self._resolve_source_images(request)

            provider_request_id = await wavespeed_service.submit(
                model=request.model,
                prompt=request.prompt,
                size=request.size,
                seed=request.seed,
                num_images=request.num_images,
                strength=request.strength,
                images=source_images,
            )

            file_id = self._build_wavespeed_file_id(provider_request_id, request)
            await registry.create_job(
                file_id=file_id,
                provider_request_id=provider_request_id,
                model=request.model,
                prompt=request.prompt,
                remove_background=request.remove_background,
            )

            processing_time = int((time.time() - start_time) * 1000)
            return JSONResponse(
                status_code=202,
                content={
                    "file_id": file_id,
                    "status": "pending",
                    "provider_request_id": provider_request_id,
                },
                headers={
                    "X-Processing-Time-Ms": str(processing_time),
                    "Content-Type": "application/json",
                },
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error submitting WaveSpeed generation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to submit WaveSpeed generation: {str(e)}")

    async def _resolve_source_images(self, request: WaveSpeedGenerateRequest) -> List[str]:
        """Resolve source images from uploaded IDs and source URLs."""
        source_images: List[str] = []

        for image_id in request.source_image_ids or []:
            cached = await self.cache_manager.get_uploaded_image(image_id)
            if not cached:
                raise HTTPException(status_code=404, detail=f"Uploaded image not found: {image_id}")
            image_bytes, _ = cached
            source_images.append(base64.b64encode(image_bytes).decode("utf-8"))

        for source_url in request.source_image_urls or []:
            # Nano Banana edit model accepts source image URL directly.
            if request.model == "nanabanana":
                source_images.append(source_url)
                continue

            image_bytes = await self.wavespeed_service.client.download_image(source_url)
            if not image_bytes:
                raise HTTPException(status_code=400, detail=f"Failed to download source URL: {source_url}")
            source_images.append(base64.b64encode(image_bytes).decode("utf-8"))

        return source_images

    async def get_wavespeed_sticker(self, file_id: str):
        """Download generated sticker by ws_ file_id."""
        start_time = time.time()

        if not file_id.startswith("ws_"):
            raise HTTPException(status_code=400, detail="WaveSpeed file_id must start with 'ws_'")

        cached = await self.cache_manager.get_sticker_from_cache_only(file_id)
        if cached:
            content, mime_type, was_converted = cached
            processing_time = int((time.time() - start_time) * 1000)
            headers = build_sticker_response_headers(file_id, was_converted, len(content), processing_time)
            return StreamingResponse(io.BytesIO(content), media_type=mime_type, headers=headers)

        registry = self.wavespeed_registry
        job = await registry.get_job(file_id)
        if not job:
            raise HTTPException(status_code=404, detail="WaveSpeed job not found")

        if self._is_job_expired(job):
            raise HTTPException(status_code=410, detail="WaveSpeed job has expired")

        terminal_status = await self._refresh_wavespeed_job_status(file_id, job)
        if terminal_status == "pending":
            return JSONResponse(status_code=202, content={"file_id": file_id, "status": "pending"})
        if terminal_status == "failed":
            updated_job = await registry.get_job(file_id)
            raise self._map_wavespeed_error_to_http(updated_job)

        content, mime_type = await self._materialize_wavespeed_job(file_id)

        processing_time = int((time.time() - start_time) * 1000)
        headers = build_sticker_response_headers(file_id, False, len(content), processing_time)
        return StreamingResponse(io.BytesIO(content), media_type=mime_type, headers=headers)

    async def save_wavespeed_sticker_to_set(self, request: WaveSpeedSaveToSetRequest) -> JSONResponse:
        """Wait for WaveSpeed sticker readiness and save it to Telegram sticker set."""
        content, mime_type = await self._await_wavespeed_sticker_ready(
            file_id=request.file_id,
            timeout_sec=request.wait_timeout_sec,
        )
        if mime_type != "image/webp":
            raise HTTPException(status_code=422, detail="Only static WEBP stickers are supported for saving to set")

        idempotency_key = self._build_ws_save_to_set_idempotency_key(request, content)
        cached_result = await self._get_ws_save_to_set_idempotency_result(idempotency_key)
        if cached_result:
            return JSONResponse(
                status_code=200,
                content={
                    "file_id": request.file_id,
                    "telegram_file_id": cached_result.get("telegram_file_id"),
                    "set_name": cached_result.get("name", request.name),
                    "title": request.title,
                    "emoji": request.emoji,
                    "result": cached_result,
                    "status": "saved",
                    "deduplicated": True,
                },
            )

        try:
            result = await self.cache_manager.telegram_service.save_sticker_to_set(
                user_id=request.user_id,
                name=request.name,
                title=request.title,
                emoji=request.emoji,
                sticker_bytes=content,
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except TelegramAPIError as te:
            raise HTTPException(status_code=te.status, detail=te.description)

        await self._set_ws_save_to_set_idempotency_result(idempotency_key, result)

        return JSONResponse(
            status_code=200,
            content={
                "file_id": request.file_id,
                "telegram_file_id": result.get("telegram_file_id"),
                "set_name": result.get("name", request.name),
                "title": request.title,
                "emoji": request.emoji,
                "result": result,
                "status": "saved",
                "deduplicated": False,
            },
        )

    def _build_ws_save_to_set_idempotency_key(
        self,
        request: WaveSpeedSaveToSetRequest,
        sticker_bytes: bytes,
    ) -> str:
        payload_fingerprint = "|".join(
            [
                str(request.user_id),
                request.name.strip().lower(),
                hashlib.sha256(sticker_bytes).hexdigest(),
            ]
        )
        digest = hashlib.sha256(payload_fingerprint.encode("utf-8")).hexdigest()
        return f"wavespeed:save_to_set:idempotency:{digest}"

    async def _get_ws_save_to_set_idempotency_result(self, idempotency_key: str) -> Optional[dict]:
        redis_client = getattr(getattr(self.cache_manager, "redis_service", None), "redis", None)
        if redis_client:
            try:
                raw = await redis_client.get(idempotency_key)
                if raw:
                    if isinstance(raw, bytes):
                        return json.loads(raw.decode("utf-8"))
                    return json.loads(raw)
            except Exception as e:
                logger.warning(f"Failed to read idempotency cache from Redis: {e}")

        return self._ws_save_to_set_idempotency_cache.get(idempotency_key)

    async def _set_ws_save_to_set_idempotency_result(self, idempotency_key: str, result: dict) -> None:
        redis_client = getattr(getattr(self.cache_manager, "redis_service", None), "redis", None)
        payload = json.dumps(result)
        if redis_client:
            try:
                ttl_seconds = 7 * 24 * 60 * 60
                await redis_client.setex(idempotency_key, ttl_seconds, payload.encode("utf-8"))
            except Exception as e:
                logger.warning(f"Failed to store idempotency cache in Redis: {e}")

        # In-memory fallback for deployments without Redis.
        self._ws_save_to_set_idempotency_cache[idempotency_key] = result

    async def _await_wavespeed_sticker_ready(self, *, file_id: str, timeout_sec: int) -> Tuple[bytes, str]:
        """Wait for generated sticker to become ready in cache and return content."""
        deadline = time.time() + timeout_sec
        registry = self.wavespeed_registry

        while True:
            cached = await self.cache_manager.get_sticker_from_cache_only(file_id)
            if cached:
                return cached[0], cached[1]

            job = await registry.get_job(file_id)
            if not job:
                raise HTTPException(status_code=404, detail="WaveSpeed job not found")
            if self._is_job_expired(job):
                raise HTTPException(status_code=410, detail="WaveSpeed job has expired")

            terminal_status = await self._refresh_wavespeed_job_status(file_id, job)
            if terminal_status == "ready":
                return await self._materialize_wavespeed_job(file_id)
            if terminal_status == "failed":
                updated_job = await registry.get_job(file_id)
                raise self._map_wavespeed_error_to_http(updated_job)

            remaining = deadline - time.time()
            if remaining <= 0:
                raise HTTPException(
                    status_code=202,
                    detail={"file_id": file_id, "status": "pending", "message": "Generation is still in progress"},
                )
            await asyncio.sleep(min(1.0, remaining))

    async def _refresh_wavespeed_job_status(self, file_id: str, job: dict) -> str:
        """Poll WaveSpeed once and synchronize local registry state."""
        if job["status"] in {"failed", "ready"}:
            return "failed" if job["status"] == "failed" else "ready"

        service = self.wavespeed_service
        registry = self.wavespeed_registry
        result = await service.poll_once(job["provider_request_id"])
        if not result:
            return "pending"

        status = service.extract_status(result)
        if status == "completed":
            source_url = service.extract_output_url(result)
            if not source_url:
                await registry.set_failed(file_id, {"code": "missing_output_url", "message": "WaveSpeed returned no output URL"})
                return "failed"
            await registry.set_completed(file_id, source_url)
            return "ready"

        if status == "failed":
            await registry.set_failed(file_id, {"code": "generation_failed", "message": service.extract_error(result)})
            return "failed"

        await registry.set_pending(file_id)
        return "pending"

    async def _materialize_wavespeed_job(self, file_id: str) -> Tuple[bytes, str]:
        """Download, post-process, normalize and cache generated image."""
        async with self._ws_materialize_semaphore:
            lock = self._ws_locks.setdefault(file_id, asyncio.Lock())
            async with lock:
                # Double-check cache after waiting for lock.
                cached = await self.cache_manager.get_sticker_from_cache_only(file_id)
                if cached:
                    return cached[0], cached[1]

                registry = self.wavespeed_registry
                job = await registry.get_job(file_id)
                if not job or not job.get("source_url"):
                    raise HTTPException(status_code=202, detail="WaveSpeed job is not ready yet")

                service = self.wavespeed_service
                image_bytes = await service.client.download_image(job["source_url"])
                if not image_bytes:
                    await registry.set_failed(file_id, {"code": "download_failed", "message": "Failed to download generated image"})
                    raise HTTPException(status_code=424, detail="Failed to download generated image")

                if job.get("remove_background"):
                    image_bytes = await self._apply_background_removal(file_id, job)

                normalized_bytes, mime_type = self._sticker_normalizer.normalize_to_webp(image_bytes)
                await self.cache_manager.store_generated_sticker(
                    file_id=file_id,
                    content=normalized_bytes,
                    output_format="webp",
                    mime_type=mime_type,
                )
                await registry.set_ready(file_id)
                return normalized_bytes, mime_type

    async def _apply_background_removal(self, file_id: str, job: dict) -> bytes:
        """Apply WaveSpeed background remover for generated image."""
        service = self.wavespeed_service
        registry = self.wavespeed_registry

        # Background remover expects URL, so we use source_url result from generation.
        bg_request_id = await service.client.submit_background_remover(job["source_url"])
        bg_result = await service.poll_until_terminal(
            bg_request_id,
            timeout_sec=settings.wavespeed_poll_timeout_sec,
            interval_sec=1.0,
        )
        if not bg_result:
            await registry.set_failed(file_id, {"code": "background_removal_timeout", "message": "Background remover timeout"})
            raise HTTPException(status_code=424, detail="Background remover timeout")

        bg_status = service.extract_status(bg_result)
        if bg_status != "completed":
            await registry.set_failed(file_id, {"code": "background_removal_failed", "message": service.extract_error(bg_result)})
            raise HTTPException(status_code=424, detail="Background remover failed")

        bg_url = service.extract_output_url(bg_result)
        if not bg_url:
            await registry.set_failed(file_id, {"code": "background_removal_missing_output", "message": "Background remover returned no output URL"})
            raise HTTPException(status_code=424, detail="Background remover returned no output URL")

        bg_bytes = await service.client.download_image(bg_url)
        if not bg_bytes:
            await registry.set_failed(file_id, {"code": "background_removal_download_failed", "message": "Failed to download background-removed image"})
            raise HTTPException(status_code=424, detail="Failed to download background-removed image")
        return bg_bytes

    def _build_wavespeed_file_id(self, provider_request_id: str, request: WaveSpeedGenerateRequest) -> str:
        """Build namespaced synthetic file_id for WaveSpeed generated assets."""
        fingerprint = "|".join(
            [
                provider_request_id,
                request.model,
                request.size,
                str(request.remove_background),
                str(int(datetime.utcnow().timestamp())),
            ]
        )
        return f"ws_{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]}"

    def _is_job_expired(self, job: dict) -> bool:
        expires_at = job.get("expires_at")
        if not expires_at:
            return False
        try:
            return datetime.utcnow() > datetime.fromisoformat(expires_at)
        except ValueError:
            return False

    def _map_wavespeed_error_to_http(self, job: Optional[dict]) -> HTTPException:
        payload = (job or {}).get("error_payload") or {}
        code = payload.get("code", "wavespeed_failed")
        message = payload.get("message", "WaveSpeed processing failed")
        # 424 for upstream processing errors, 422 for semantic failures.
        status_code = 424 if "download" in code or "background" in code or "generation" in code else 422
        return HTTPException(status_code=status_code, detail={"code": code, "message": message})
    
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

