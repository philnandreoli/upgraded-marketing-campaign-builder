"""
Azure AI image generation service with retry + feature flag guard.
"""

from __future__ import annotations

import base64
import logging
import re

import aiohttp
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import get_settings

logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


class ImageGenerationService:
    """Generates image bytes from prompts using Azure AI image generation."""

    MAX_PROMPT_LENGTH = 4000
    _DEFAULT_MODEL = "gpt-image-1"

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.image_generation

        self._enabled = cfg.enabled
        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(
            endpoint=cfg.azure_ai_image_endpoint,
            credential=self._credential,
        )
        self._client = self._project_client.get_openai_client()

    @staticmethod
    def _sanitize_prompt(prompt: str) -> str:
        cleaned = _CONTROL_CHARS_RE.sub("", prompt).strip()
        if not cleaned:
            raise ValueError("Image generation prompt cannot be empty.")
        if len(cleaned) > ImageGenerationService.MAX_PROMPT_LENGTH:
            cleaned = cleaned[: ImageGenerationService.MAX_PROMPT_LENGTH]
        return cleaned

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def generate(self, prompt: str, dimensions: str = "1024x1024") -> bytes:
        """Generate image bytes for *prompt* and return raw bytes."""
        if not self._enabled:
            raise RuntimeError(
                "Image generation is disabled. Set IMAGE_GENERATION_ENABLED=true to enable this feature."
            )

        sanitized_prompt = self._sanitize_prompt(prompt)

        logger.debug("Image generation request — dimensions=%s", dimensions)
        response = await self._client.images.generate(
            model=self._DEFAULT_MODEL,
            prompt=sanitized_prompt,
            size=dimensions,
        )

        image_data = response.data[0]
        b64_json = getattr(image_data, "b64_json", None)
        if b64_json:
            return base64.b64decode(b64_json)

        image_url = getattr(image_data, "url", None)
        if image_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as url_response:
                    url_response.raise_for_status()
                    return await url_response.read()

        raise RuntimeError("Image generation response did not contain image data.")

    async def close(self) -> None:
        """Clean up underlying clients and credential."""
        await self._client.close()
        await self._project_client.close()
        await self._credential.close()


_image_generation_service: ImageGenerationService | None = None


def get_image_generation_service() -> ImageGenerationService:
    """Return (and lazily create) the global ImageGenerationService instance."""
    global _image_generation_service
    if _image_generation_service is None:
        _image_generation_service = ImageGenerationService()
    return _image_generation_service

