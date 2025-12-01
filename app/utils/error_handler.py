"""Centralized error handling utilities."""
import logging
from typing import Optional
from fastapi import HTTPException

from app.services.telegram_enhanced import TelegramAPIError

logger = logging.getLogger(__name__)


def handle_telegram_api_error(
    error: TelegramAPIError,
    file_id: str,
    elapsed_time_ms: int
) -> HTTPException:
    """
    Handle Telegram API errors and convert to HTTP exceptions.
    
    Args:
        error: TelegramAPIError instance
        file_id: File ID for logging
        elapsed_time_ms: Elapsed time in milliseconds
        
    Returns:
        HTTPException with appropriate status code
    """
    # Log client errors (4xx) as warnings, server errors (5xx) as errors
    if 400 <= error.status < 500:
        logger.warning(
            f"Telegram API client error for {file_id}: [{error.status}] {error.description} "
            f"(elapsed: {elapsed_time_ms}ms)"
        )
    else:
        logger.error(
            f"Telegram API error for {file_id}: [{error.status}] {error.description} "
            f"(elapsed: {elapsed_time_ms}ms)"
        )
    
    return HTTPException(status_code=error.status, detail=error.description)


def handle_timeout_error(
    file_id: str,
    elapsed_time_ms: int,
    timeout_seconds: int
) -> HTTPException:
    """
    Handle timeout errors.
    
    Args:
        file_id: File ID for logging
        elapsed_time_ms: Elapsed time in milliseconds
        timeout_seconds: Timeout limit in seconds
        
    Returns:
        HTTPException with 504 status code
    """
    logger.error(
        f"Request timeout for sticker {file_id} after {elapsed_time_ms}ms "
        f"(timeout limit: {timeout_seconds}s)"
    )
    return HTTPException(
        status_code=504,
        detail=f"Request timeout: processing exceeded {timeout_seconds} seconds. "
               f"This may occur when fetching new stickers from Telegram API. "
               f"Please try again later or check if the file_id is valid."
    )


def handle_generic_error(
    error: Exception,
    file_id: str,
    elapsed_time_ms: int
) -> HTTPException:
    """
    Handle generic errors.
    
    Args:
        error: Exception instance
        file_id: File ID for logging
        elapsed_time_ms: Elapsed time in milliseconds
        
    Returns:
        HTTPException with 500 status code
    """
    logger.error(
        f"Error processing sticker {file_id} after {elapsed_time_ms}ms: {error}",
        exc_info=True
    )
    return HTTPException(status_code=500, detail="Internal server error")

