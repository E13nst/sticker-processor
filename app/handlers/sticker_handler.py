"""Handler for sticker-related business logic."""
import time
import logging
import asyncio
import io
from typing import Optional, Tuple
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.services.cache_manager import CacheManager
from app.services.telegram_enhanced import TelegramAPIError
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

