"""Compatibility shim — auth has moved to backend.infrastructure.auth."""
from backend.infrastructure.auth import *  # noqa: F401, F403
from backend.infrastructure.auth import (  # noqa: F401
    get_current_user, require_admin, require_authenticated,
    require_campaign_builder, validate_token, _provision_user,
)
