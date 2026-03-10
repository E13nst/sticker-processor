"""WaveSpeed generation orchestration service."""
import asyncio
from typing import Any, Dict, Optional

from app.config import settings
from wavespeed_client import WaveSpeedClient


class WaveSpeedGenerationService:
    """High-level wrapper around WaveSpeed client with polling helpers."""

    def __init__(self):
        if not settings.wavespeed_api_key:
            raise ValueError("WAVESPEED_API_KEY is not configured.")
        self.client = WaveSpeedClient(settings.wavespeed_api_key)

    async def submit(self, *, model: str, prompt: str, size: str, seed: int, num_images: int, strength: float, image: str) -> str:
        return await self.client.submit_generation(
            model=model,
            final_prompt=prompt,
            size=size,
            seed=seed,
            num_images=num_images,
            strength=strength,
            image=image,
            output_format="png",
        )

    async def poll_once(self, request_id: str) -> Optional[Dict[str, Any]]:
        return await self.client.get_prediction_result(request_id)

    async def poll_until_terminal(self, request_id: str, timeout_sec: int = 20, interval_sec: float = 1.0) -> Optional[Dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            data = await self.poll_once(request_id)
            if not data:
                return None
            payload = data.get("data", data)
            status = payload.get("status")
            if status in {"completed", "failed"}:
                return data
            await asyncio.sleep(interval_sec)
        return await self.poll_once(request_id)

    @staticmethod
    def extract_status(data: Dict[str, Any]) -> str:
        payload = data.get("data", data)
        return payload.get("status", "unknown")

    @staticmethod
    def extract_output_url(data: Dict[str, Any]) -> Optional[str]:
        payload = data.get("data", data)
        outputs = payload.get("outputs") or []
        if outputs:
            return outputs[0]
        return None

    @staticmethod
    def extract_error(data: Dict[str, Any]) -> str:
        payload = data.get("data", data)
        return payload.get("error", "WaveSpeed generation failed")

    async def close(self):
        await self.client.close()
