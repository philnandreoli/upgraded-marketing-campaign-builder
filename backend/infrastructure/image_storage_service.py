"""
Azure Blob storage service for generated campaign images.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient

from backend.config import get_settings


class ImageStorageService:
    """Uploads generated images and returns storage path + temporary access URL."""

    _SAS_TTL_MINUTES = 60

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.image_generation

        self._account_url = cfg.azure_storage_account_url
        self._container = cfg.azure_storage_container
        self._credential = DefaultAzureCredential()
        self._blob_service_client = BlobServiceClient(
            account_url=self._account_url,
            credential=self._credential,
        )

    async def upload(
        self,
        campaign_id: str,
        asset_id: str,
        image_bytes: bytes,
        fmt: str = "png",
    ) -> tuple[str, str]:
        """Upload image and return (storage_path, time-limited image_url)."""
        fmt_normalized = fmt.lower().strip(".") or "png"
        storage_path = f"campaigns/{campaign_id}/{asset_id}.{fmt_normalized}"

        container_client = self._blob_service_client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(storage_path)
        await blob_client.upload_blob(
            image_bytes,
            overwrite=True,
            content_type=f"image/{fmt_normalized}",
        )

        image_url = await self._generate_sas_url(storage_path)
        return storage_path, image_url

    async def generate_sas_url(self, storage_path: str) -> str:
        """Generate a fresh time-limited SAS URL for an existing blob."""
        return await self._generate_sas_url(storage_path)

    async def _generate_sas_url(self, storage_path: str) -> str:
        """Internal helper: create a SAS-signed URL for *storage_path*."""
        container_client = self._blob_service_client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(storage_path)

        starts_on = datetime.now(UTC)
        expires_on = starts_on + timedelta(minutes=self._SAS_TTL_MINUTES)
        user_delegation_key = await self._blob_service_client.get_user_delegation_key(
            key_start_time=starts_on,
            key_expiry_time=expires_on,
        )

        account_name = self._blob_service_client.account_name
        if not account_name:
            raise RuntimeError("Storage account name is not available for SAS generation.")

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self._container,
            blob_name=storage_path,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expires_on,
            start=starts_on,
        )
        image_url = f"{blob_client.url}?{sas_token}"
        return image_url

    async def close(self) -> None:
        """Release underlying clients and credential."""
        await self._blob_service_client.close()
        await self._credential.close()


_image_storage_service: ImageStorageService | None = None


def get_image_storage_service() -> ImageStorageService:
    """Return (and lazily create) the global ImageStorageService instance."""
    global _image_storage_service
    if _image_storage_service is None:
        _image_storage_service = ImageStorageService()
    return _image_storage_service

