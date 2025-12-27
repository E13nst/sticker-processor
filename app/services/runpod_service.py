"""RunPod service for generating stickers via Snapstix."""
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
from aiohttp import ClientTimeout

from app.config import settings

logger = logging.getLogger(__name__)

# Create a separate logger for detailed API interactions
api_logger = logging.getLogger(f"{__name__}.api")
api_logger.setLevel(logging.DEBUG)

# Template file path (example.json in project root)
TEMPLATE_PATH = Path(__file__).parent.parent.parent / "example.json"


class RunPodService:
    """Service for interacting with RunPod API to generate stickers via Snapstix."""
    
    def __init__(self):
        """Initialize RunPod service."""
        self.template_cache: Optional[Dict[str, Any]] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self.api_url = settings.runpod_api_url
        self.api_token = settings.runpod_api_token
        
        if not self.api_token:
            logger.warning(
                "RunPod API token not configured. API requests may fail with 401 Unauthorized. "
                "Please set RUNPOD_API_TOKEN in environment variables."
            )
    
    def _load_template(self) -> Dict[str, Any]:
        """
        Load template from example.json file.
        
        Returns:
            Template dictionary
            
        Raises:
            FileNotFoundError: If template file doesn't exist
            ValueError: If template file is invalid JSON
        """
        if self.template_cache is not None:
            return self.template_cache
        
        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError(
                f"Template file not found: {TEMPLATE_PATH}. "
                f"Please ensure example.json exists in the project root."
            )
        
        try:
            with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                template = json.load(f)
            self.template_cache = template
            logger.info(f"Loaded template from {TEMPLATE_PATH}")
            return template
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in template file: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to load template file: {e}") from e
    
    def _substitute_template(self, template: Dict[str, Any], prompt: str, processing_id: str, callback_url: str) -> Dict[str, Any]:
        """
        Substitute placeholders in template with actual values.
        
        Args:
            template: Template dictionary
            prompt: Text prompt for generation
            processing_id: Processing job ID (UUID)
            callback_url: Callback URL
            
        Returns:
            Dictionary with substituted values
        """
        # Deep copy template to avoid modifying the original
        payload = json.loads(json.dumps(template))
        
        # Substitute placeholders in JSON structure
        def replace_placeholders(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: replace_placeholders(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_placeholders(item) for item in obj]
            elif isinstance(obj, str):
                # Replace placeholders in strings
                return (obj
                       .replace("{{prompt}}", prompt)
                       .replace("{{processing_id}}", processing_id)
                       .replace("{{callback_url}}", callback_url))
            else:
                return obj
        
        payload = replace_placeholders(payload)
        return payload
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=30)  # 30 seconds timeout
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.debug("Created aiohttp session for RunPod API")
        
        return self._session
    
    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Closed aiohttp session for RunPod API")
    
    async def generate_sticker(
        self,
        prompt: str,
        callback_url: str,
        processing_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a sticker by sending request to RunPod API.
        
        Args:
            prompt: Text prompt for sticker generation
            callback_url: URL to receive callback with generated image
            processing_id: Optional processing job ID. If not provided, UUID will be generated
            
        Returns:
            Response dictionary from RunPod API (typically contains job ID and status)
            
        Raises:
            ValueError: If template loading or substitution fails
            aiohttp.ClientError: If HTTP request fails
            asyncio.TimeoutError: If request times out
        """
        # Generate UUID if processing_id not provided
        if processing_id is None:
            processing_id = str(uuid.uuid4())
            logger.debug(f"Generated processing_id: {processing_id}")
        
        # Load template
        try:
            template = self._load_template()
        except Exception as e:
            logger.error(f"Failed to load template: {e}")
            raise ValueError(f"Failed to load template: {e}") from e
        
        # Substitute placeholders
        try:
            payload = self._substitute_template(template, prompt, processing_id, callback_url)
        except Exception as e:
            logger.error(f"Failed to substitute template: {e}")
            raise ValueError(f"Failed to substitute template: {e}") from e
        
        # Send POST request to RunPod API
        session = await self._get_session()
        
        request_id = f"runpod-{processing_id[:8]}"
        
        logger.info(
            f"[{request_id}] Sending request to RunPod API: prompt='{prompt[:50]}{'...' if len(prompt) > 50 else ''}', "
            f"processing_id={processing_id}, callback_url={callback_url}"
        )
        
        # Prepare headers
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        
        # Log request details
        api_logger.info(f"[{request_id}] 🌐 RunPod API Request")
        api_logger.debug(f"[{request_id}] URL: {self.api_url}")
        api_logger.debug(f"[{request_id}] Method: POST")
        # Log headers without sensitive token (only show if token is present)
        headers_log = dict(headers)
        if "Authorization" in headers_log:
            headers_log["Authorization"] = "Bearer ***"
        api_logger.debug(f"[{request_id}] Headers: {headers_log}")
        
        # Log request payload (formatted JSON)
        try:
            payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
            api_logger.debug(f"[{request_id}] Request Payload:\n{payload_str}")
        except Exception as e:
            api_logger.warning(f"[{request_id}] Failed to format request payload: {e}")
            api_logger.debug(f"[{request_id}] Request Payload (raw): {str(payload)[:500]}")
        
        try:
            async with session.post(
                self.api_url,
                json=payload,
                headers=headers
            ) as response:
                # Log response status and headers first
                api_logger.debug(f"[{request_id}] Response Status: {response.status}")
                api_logger.debug(f"[{request_id}] Response Headers: {dict(response.headers)}")
                
                # Read response body (try JSON first, fallback to text)
                response_text = await response.text()
                response_data = None
                
                # Try to parse as JSON for logging
                try:
                    response_data = json.loads(response_text)
                    # Log formatted JSON response
                    response_str = json.dumps(response_data, indent=2, ensure_ascii=False)
                    api_logger.debug(f"[{request_id}] Response Body:\n{response_str}")
                except json.JSONDecodeError:
                    # If not JSON, log raw text (truncated if too long)
                    response_preview = response_text[:1000] + "..." if len(response_text) > 1000 else response_text
                    api_logger.debug(f"[{request_id}] Response Body (raw, not JSON): {response_preview}")
                
                # Check HTTP status
                if response.status != 200:
                    logger.error(
                        f"[{request_id}] RunPod API returned error status {response.status}: {response_text[:200]}"
                    )
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"RunPod API error: {response_text}"
                    )
                
                # Parse JSON response (if not already parsed)
                if response_data is None:
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        logger.error(f"[{request_id}] Failed to parse RunPod API response as JSON: {response_text[:200]}")
                        raise ValueError(f"Invalid JSON response from RunPod API: {e}") from e
                
                logger.info(
                    f"[{request_id}] RunPod API request successful: processing_id={processing_id}, "
                    f"response_keys={list(response_data.keys()) if isinstance(response_data, dict) else 'N/A'}"
                )
                return response_data
                    
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error calling RunPod API: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling RunPod API: {e}")
            raise ValueError(f"Failed to call RunPod API: {e}") from e

