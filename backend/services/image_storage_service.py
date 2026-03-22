"""Compatibility shim — image_storage_service has moved to backend.infrastructure.image_storage_service."""
from backend.infrastructure.image_storage_service import *  # noqa: F401, F403
from backend.infrastructure.image_storage_service import (  # noqa: F401
    ImageStorageService,
    get_image_storage_service,
)

