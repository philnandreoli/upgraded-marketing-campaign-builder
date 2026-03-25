"""
Tests for ImageGenerationService and ImageStorageService.
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.image_generation_service import ImageGenerationService
from backend.services.image_storage_service import ImageStorageService


@pytest.fixture
def image_generation_service():
    with (
        patch("backend.infrastructure.image_generation_service.get_settings") as mock_settings,
        patch("backend.infrastructure.image_generation_service.DefaultAzureCredential") as mock_cred,
    ):
        mock_settings.return_value = MagicMock(
            image_generation=MagicMock(
                enabled=True,
                model="gpt-image-1.5",
                endpoint="https://test.openai.azure.com/openai/v1/",
                url_fetch_enabled=False,
                url_fetch_allowed_hosts=[],
                url_fetch_timeout_seconds=10.0,
                url_fetch_max_bytes=10 * 1024 * 1024,
            ),
        )
        mock_cred_instance = MagicMock()
        mock_cred_instance.get_token = AsyncMock(return_value=MagicMock(token="fake-token"))
        mock_cred.return_value = mock_cred_instance
        service = ImageGenerationService()
        # Attach a mock client that tests can configure
        service._mock_openai_client = MagicMock()
        service._mock_openai_client.close = AsyncMock()
    return service


def _patch_get_client(service, mock_response=None, side_effect=None):
    """Helper to patch _get_client to return a mock OpenAI client."""
    mock_client = service._mock_openai_client
    if side_effect:
        mock_client.images.generate = AsyncMock(side_effect=side_effect)
    elif mock_response:
        mock_client.images.generate = AsyncMock(return_value=mock_response)
    service._get_client = AsyncMock(return_value=mock_client)
    return mock_client


class TestImageGenerationService:
    @pytest.mark.asyncio
    async def test_generate_returns_bytes_from_b64(self, image_generation_service):
        expected = b"fake-image-bytes"
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(expected).decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        mock_client = _patch_get_client(image_generation_service, mock_response=mock_response)

        result = await image_generation_service.generate("A lighthouse at sunset")

        assert result == expected
        kwargs = mock_client.images.generate.call_args[1]
        assert kwargs["model"] == "gpt-image-1.5"
        assert kwargs["size"] == "1024x1024"

    @pytest.mark.asyncio
    async def test_generate_sanitizes_prompt_and_truncates(self, image_generation_service):
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(b"x").decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        mock_client = _patch_get_client(image_generation_service, mock_response=mock_response)

        prompt = "\x00Hello\x1f " + ("A" * (ImageGenerationService.MAX_PROMPT_LENGTH + 20))
        await image_generation_service.generate(prompt, dimensions="1536x1024")

        kwargs = mock_client.images.generate.call_args[1]
        assert "\x00" not in kwargs["prompt"]
        assert "\x1f" not in kwargs["prompt"]
        assert len(kwargs["prompt"]) == ImageGenerationService.MAX_PROMPT_LENGTH
        assert kwargs["size"] == "1536x1024"

    @pytest.mark.asyncio
    async def test_generate_raises_when_disabled(self):
        with (
            patch("backend.infrastructure.image_generation_service.get_settings") as mock_settings,
            patch("backend.infrastructure.image_generation_service.DefaultAzureCredential") as mock_cred,
        ):
            mock_settings.return_value = MagicMock(
                image_generation=MagicMock(
                    enabled=False,
                    model="gpt-image-1.5",
                    endpoint="https://test.openai.azure.com/openai/v1/",
                ),
            )
            mock_cred.return_value = MagicMock()
            service = ImageGenerationService()

        with pytest.raises(RuntimeError, match="Image generation is disabled"):
            await service.generate("test")

    @pytest.mark.asyncio
    async def test_generate_retries_on_transient_failure(self, image_generation_service):
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(b"ok").decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        mock_client = _patch_get_client(
            image_generation_service,
            side_effect=[Exception("transient"), mock_response],
        )

        result = await image_generation_service.generate("test")
        assert result == b"ok"
        assert mock_client.images.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_raises_after_max_retries(self, image_generation_service):
        mock_client = _patch_get_client(
            image_generation_service,
            side_effect=Exception("permanent"),
        )

        with pytest.raises(Exception, match="permanent"):
            await image_generation_service.generate("test")
        assert mock_client.images.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_rejects_empty_prompt_after_sanitization(self, image_generation_service):
        with pytest.raises(ValueError, match="cannot be empty"):
            await image_generation_service.generate("\x00\x1f   ")

    @pytest.mark.asyncio
    async def test_generate_raises_when_only_url_returned_and_fallback_disabled(self, image_generation_service):
        mock_image = MagicMock()
        mock_image.b64_json = None
        mock_image.url = "https://test.openai.azure.com/images/1"
        mock_response = MagicMock(data=[mock_image])
        _patch_get_client(image_generation_service, mock_response=mock_response)

        with pytest.raises(RuntimeError, match="URL fetch fallback is disabled"):
            await image_generation_service.generate("test")

    @pytest.mark.asyncio
    async def test_generate_fetches_url_when_fallback_enabled(self, image_generation_service):
        image_generation_service._url_fetch_enabled = True
        mock_image = MagicMock()
        mock_image.b64_json = None
        mock_image.url = "https://test.openai.azure.com/images/1"
        mock_response = MagicMock(data=[mock_image])
        _patch_get_client(image_generation_service, mock_response=mock_response)
        image_generation_service._fetch_image_url_bytes = AsyncMock(return_value=b"img")

        result = await image_generation_service.generate("test")

        assert result == b"img"
        image_generation_service._fetch_image_url_bytes.assert_awaited_once_with(mock_image.url)

    def test_validate_image_url_rejects_non_https_and_non_allowlisted_hosts(self, image_generation_service):
        image_generation_service._url_fetch_allowed_hosts = {"test.openai.azure.com"}

        with pytest.raises(RuntimeError, match="requires HTTPS"):
            image_generation_service._validate_image_url("http://test.openai.azure.com/images/1")

        with pytest.raises(RuntimeError, match="not allowlisted"):
            image_generation_service._validate_image_url("https://evil.example.com/images/1")

        with pytest.raises(RuntimeError, match="port 443"):
            image_generation_service._validate_image_url("https://test.openai.azure.com:444/images/1")


class TestImageGenerationServiceAccessor:
    def test_get_image_generation_service_is_singleton(self):
        import backend.infrastructure.image_generation_service as module

        with patch.object(module, "ImageGenerationService") as mock_service:
            module._image_generation_service = None
            instance = MagicMock()
            mock_service.return_value = instance

            first = module.get_image_generation_service()
            second = module.get_image_generation_service()

        assert first is instance
        assert second is instance
        mock_service.assert_called_once()


class TestImageStorageService:
    @pytest.mark.asyncio
    async def test_upload_returns_storage_path_and_sas_url(self):
        with (
            patch("backend.infrastructure.image_storage_service.get_settings") as mock_settings,
            patch("backend.infrastructure.image_storage_service.DefaultAzureCredential"),
            patch("backend.infrastructure.image_storage_service.BlobServiceClient") as mock_blob_service,
            patch("backend.infrastructure.image_storage_service.generate_blob_sas", return_value="sig=abc"),
        ):
            mock_settings.return_value = MagicMock(
                image_generation=MagicMock(
                    azure_storage_account_url="https://acct.blob.core.windows.net",
                    azure_storage_container="campaign-images",
                )
            )

            blob_service = MagicMock()
            blob_service.account_name = "acct"
            blob_service.get_user_delegation_key = AsyncMock(return_value=MagicMock())
            mock_blob_service.return_value = blob_service

            container_client = MagicMock()
            blob_client = MagicMock()
            blob_client.url = "https://acct.blob.core.windows.net/campaign-images/campaigns/c1/a1.png"
            blob_client.upload_blob = AsyncMock()
            container_client.get_blob_client.return_value = blob_client
            blob_service.get_container_client.return_value = container_client

            service = ImageStorageService()
            storage_path, image_url = await service.upload("c1", "a1", b"img", fmt="png")

        assert storage_path == "campaigns/c1/a1.png"
        assert image_url == f"{blob_client.url}?sig=abc"
        blob_client.upload_blob.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_normalizes_format(self):
        with (
            patch("backend.infrastructure.image_storage_service.get_settings") as mock_settings,
            patch("backend.infrastructure.image_storage_service.DefaultAzureCredential"),
            patch("backend.infrastructure.image_storage_service.BlobServiceClient") as mock_blob_service,
            patch("backend.infrastructure.image_storage_service.generate_blob_sas", return_value="sig=abc"),
        ):
            mock_settings.return_value = MagicMock(
                image_generation=MagicMock(
                    azure_storage_account_url="https://acct.blob.core.windows.net",
                    azure_storage_container="campaign-images",
                )
            )

            blob_service = MagicMock()
            blob_service.account_name = "acct"
            blob_service.get_user_delegation_key = AsyncMock(return_value=MagicMock())
            mock_blob_service.return_value = blob_service

            container_client = MagicMock()
            blob_client = MagicMock()
            blob_client.url = "https://example/blob"
            blob_client.upload_blob = AsyncMock()
            container_client.get_blob_client.return_value = blob_client
            blob_service.get_container_client.return_value = container_client

            service = ImageStorageService()
            storage_path, _ = await service.upload("c1", "a1", b"img", fmt=".JPG")

        assert storage_path == "campaigns/c1/a1.jpg"
        container_client.get_blob_client.assert_called_with("campaigns/c1/a1.jpg")

    @pytest.mark.asyncio
    async def test_upload_raises_when_account_name_missing(self):
        with (
            patch("backend.infrastructure.image_storage_service.get_settings") as mock_settings,
            patch("backend.infrastructure.image_storage_service.DefaultAzureCredential"),
            patch("backend.infrastructure.image_storage_service.BlobServiceClient") as mock_blob_service,
            patch("backend.infrastructure.image_storage_service.generate_blob_sas"),
        ):
            mock_settings.return_value = MagicMock(
                image_generation=MagicMock(
                    azure_storage_account_url="https://acct.blob.core.windows.net",
                    azure_storage_container="campaign-images",
                )
            )

            blob_service = MagicMock()
            blob_service.account_name = ""
            blob_service.get_user_delegation_key = AsyncMock(return_value=MagicMock())
            mock_blob_service.return_value = blob_service

            container_client = MagicMock()
            blob_client = MagicMock()
            blob_client.url = "https://example/blob"
            blob_client.upload_blob = AsyncMock()
            container_client.get_blob_client.return_value = blob_client
            blob_service.get_container_client.return_value = container_client

            service = ImageStorageService()
            with pytest.raises(RuntimeError, match="account name"):
                await service.upload("c1", "a1", b"img")


class TestImageStorageServiceAccessor:
    def test_get_image_storage_service_is_singleton(self):
        import backend.infrastructure.image_storage_service as module

        with patch.object(module, "ImageStorageService") as mock_service:
            module._image_storage_service = None
            instance = MagicMock()
            mock_service.return_value = instance

            first = module.get_image_storage_service()
            second = module.get_image_storage_service()

        assert first is instance
        assert second is instance
        mock_service.assert_called_once()
