"""Compatibility shim — event_publisher has moved to backend.infrastructure.event_publisher."""
from backend.infrastructure.event_publisher import *  # noqa: F401, F403
from backend.infrastructure.event_publisher import (  # noqa: F401
    EventPublisher, InProcessEventPublisher, PostgresEventPublisher,
    _NOTIFY_MAX_BYTES,
)
