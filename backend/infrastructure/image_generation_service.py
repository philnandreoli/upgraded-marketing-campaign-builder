"""
Azure AI image generation service with retry + feature flag guard.
"""

from __future__ import annotations

import base64
import logging
import re

import aiohttp
from azure.identity.aio import DefaultAzureCredential
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import get_settings

logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")

_AZURE_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


class ImageGenerationService:
    """Generates image bytes from prompts using Azure AI image generation."""

    MAX_PROMPT_LENGTH = 4000

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.image_generation

        self._enabled = cfg.enabled
        self._model = cfg.model
        self._credential = DefaultAzureCredential()
        self._endpoint = cfg.endpoint

    async def _get_client(self) -> AsyncOpenAI:
        """Return an AsyncOpenAI client authenticated with a fresh Azure token."""
        token = await self._credential.get_token(_AZURE_COGNITIVE_SCOPE)
        return AsyncOpenAI(
            base_url=self._endpoint,
            api_key=token.token,
        )

    @staticmethod
    def _sanitize_prompt(prompt: str) -> str:
        cleaned = _CONTROL_CHARS_RE.sub("", prompt).strip()
        if not cleaned:
            raise ValueError("Image generation prompt cannot be empty.")
        if len(cleaned) > ImageGenerationService.MAX_PROMPT_LENGTH:
            cleaned = cleaned[: ImageGenerationService.MAX_PROMPT_LENGTH]
        return cleaned

    _SUPPORTED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}

    @staticmethod
    def _normalize_dimensions(dimensions: str) -> str:
        """Map arbitrary dimensions to the closest supported size."""
        if dimensions in ImageGenerationService._SUPPORTED_SIZES:
            return dimensions
        try:
            w, h = (int(x) for x in dimensions.split("x"))
        except (ValueError, AttributeError):
            return "auto"
        ratio = w / h if h else 1.0
        if ratio > 1.15:
            return "1536x1024"  # landscape
        elif ratio < 0.85:
            return "1024x1536"  # portrait
        return "1024x1024"  # square-ish

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
        normalized_dimensions = self._normalize_dimensions(dimensions)

        client = await self._get_client()
        try:
            response = await client.images.generate(
                model=self._model,
                prompt=sanitized_prompt,
                size=normalized_dimensions,
            )
        except Exception as exc:
            raise
        finally:
            await client.close()

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
        """Clean up underlying credential."""
        await self._credential.close()


_image_generation_service: ImageGenerationService | None = None


def get_image_generation_service() -> ImageGenerationService:
    """Return (and lazily create) the global ImageGenerationService instance."""
    global _image_generation_service
    if _image_generation_service is None:
        _image_generation_service = ImageGenerationService()
    return _image_generation_service
