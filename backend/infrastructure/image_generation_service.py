"""
Azure AI image generation service with retry + feature flag guard.
"""

from __future__ import annotations

import base64
import asyncio
import ipaddress
import logging
import re
import socket
from urllib.parse import ParseResult, urlparse

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
        self._url_fetch_enabled = cfg.url_fetch_enabled
        endpoint_host = urlparse(self._endpoint).hostname
        configured_hosts = {host.lower() for host in cfg.url_fetch_allowed_hosts}
        self._url_fetch_allowed_hosts = configured_hosts | ({endpoint_host.lower()} if endpoint_host else set())
        self._url_fetch_timeout_seconds = cfg.url_fetch_timeout_seconds
        self._url_fetch_max_bytes = cfg.url_fetch_max_bytes

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

    @staticmethod
    def _ensure_public_ip(ip_str: str) -> None:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise RuntimeError("Image URL resolved to a non-public IP address.")

    def _validate_image_url(self, image_url: str) -> ParseResult:
        parsed = urlparse(image_url)
        if parsed.scheme.lower() != "https":
            raise RuntimeError("Image URL fallback requires HTTPS.")
        if parsed.port not in (None, 443):
            raise RuntimeError("Image URL fallback only allows standard HTTPS port 443.")

        hostname = (parsed.hostname or "").rstrip(".").lower()
        if not hostname:
            raise RuntimeError("Image URL fallback requires a valid hostname.")
        if hostname not in self._url_fetch_allowed_hosts:
            raise RuntimeError("Image URL host is not allowlisted.")
        return parsed

    async def _validate_url_destination(self, hostname: str, port: int) -> None:
        try:
            self._ensure_public_ip(hostname)
            return
        except ValueError:
            pass

        loop = asyncio.get_running_loop()
        try:
            addr_info = await loop.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise RuntimeError("Image URL hostname could not be resolved.") from exc

        if not addr_info:
            raise RuntimeError("Image URL hostname did not resolve to any address.")

        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            self._ensure_public_ip(sockaddr[0])

    async def _read_response_with_limit(self, url_response: aiohttp.ClientResponse) -> bytes:
        content_length = url_response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > self._url_fetch_max_bytes:
                    raise RuntimeError("Image response exceeded maximum allowed size.")
            except ValueError:
                pass

        total = 0
        chunks: list[bytes] = []
        async for chunk in url_response.content.iter_chunked(64 * 1024):
            total += len(chunk)
            if total > self._url_fetch_max_bytes:
                raise RuntimeError("Image response exceeded maximum allowed size.")
            chunks.append(chunk)
        return b"".join(chunks)

    async def _fetch_image_url_bytes(self, image_url: str) -> bytes:
        parsed = self._validate_image_url(image_url)
        await self._validate_url_destination(parsed.hostname or "", parsed.port or 443)

        timeout = aiohttp.ClientTimeout(total=self._url_fetch_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url, allow_redirects=False) as url_response:
                url_response.raise_for_status()
                return await self._read_response_with_limit(url_response)

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
            if not self._url_fetch_enabled:
                raise RuntimeError(
                    "Image generation response returned URL data, but URL fetch fallback is disabled."
                )
            return await self._fetch_image_url_bytes(image_url)

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
