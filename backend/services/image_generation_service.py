"""Compatibility shim — image_generation_service has moved to backend.infrastructure.image_generation_service."""
from backend.infrastructure.image_generation_service import *  # noqa: F401, F403
from backend.infrastructure.image_generation_service import (  # noqa: F401
    ImageGenerationService,
    get_image_generation_service,
)

