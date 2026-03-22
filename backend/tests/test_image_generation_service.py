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
        patch("backend.infrastructure.image_generation_service.DefaultAzureCredential"),
        patch("backend.infrastructure.image_generation_service.AIProjectClient") as mock_project,
    ):
        mock_settings.return_value = MagicMock(
            image_generation=MagicMock(
                enabled=True,
                azure_ai_image_endpoint="https://image.example.com",
            )
        )
        mock_openai_client = MagicMock()
        mock_project.return_value.get_openai_client.return_value = mock_openai_client
        service = ImageGenerationService()
    return service


class TestImageGenerationService:
    @pytest.mark.asyncio
    async def test_generate_returns_bytes_from_b64(self, image_generation_service):
        expected = b"fake-image-bytes"
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(expected).decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        image_generation_service._client.images.generate = AsyncMock(return_value=mock_response)

        result = await image_generation_service.generate("A lighthouse at sunset")

        assert result == expected
        kwargs = image_generation_service._client.images.generate.call_args[1]
        assert kwargs["model"] == "gpt-image-1"
        assert kwargs["size"] == "1024x1024"

    @pytest.mark.asyncio
    async def test_generate_sanitizes_prompt_and_truncates(self, image_generation_service):
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(b"x").decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        image_generation_service._client.images.generate = AsyncMock(return_value=mock_response)

        prompt = "\x00Hello\x1f " + ("A" * (ImageGenerationService.MAX_PROMPT_LENGTH + 20))
        await image_generation_service.generate(prompt, dimensions="512x512")

        kwargs = image_generation_service._client.images.generate.call_args[1]
        assert "\x00" not in kwargs["prompt"]
        assert "\x1f" not in kwargs["prompt"]
        assert len(kwargs["prompt"]) == ImageGenerationService.MAX_PROMPT_LENGTH
        assert kwargs["size"] == "512x512"

    @pytest.mark.asyncio
    async def test_generate_raises_when_disabled(self):
        with (
            patch("backend.infrastructure.image_generation_service.get_settings") as mock_settings,
            patch("backend.infrastructure.image_generation_service.DefaultAzureCredential"),
            patch("backend.infrastructure.image_generation_service.AIProjectClient") as mock_project,
        ):
            mock_settings.return_value = MagicMock(
                image_generation=MagicMock(
                    enabled=False,
                    azure_ai_image_endpoint="https://image.example.com",
                )
            )
            mock_project.return_value.get_openai_client.return_value = MagicMock()
            service = ImageGenerationService()

        with pytest.raises(RuntimeError, match="Image generation is disabled"):
            await service.generate("test")

    @pytest.mark.asyncio
    async def test_generate_retries_on_transient_failure(self, image_generation_service):
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(b"ok").decode("ascii")
        mock_response = MagicMock(data=[mock_image])
        image_generation_service._client.images.generate = AsyncMock(
            side_effect=[Exception("transient"), mock_response]
        )

        result = await image_generation_service.generate("test")
        assert result == b"ok"
        assert image_generation_service._client.images.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_raises_after_max_retries(self, image_generation_service):
        image_generation_service._client.images.generate = AsyncMock(
            side_effect=Exception("permanent")
        )

        with pytest.raises(Exception, match="permanent"):
            await image_generation_service.generate("test")
        assert image_generation_service._client.images.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_rejects_empty_prompt_after_sanitization(self, image_generation_service):
        with pytest.raises(ValueError, match="cannot be empty"):
            await image_generation_service.generate("\x00\x1f   ")


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
        container_client.get_blob_client.assert_called_once_with("campaigns/c1/a1.jpg")

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
