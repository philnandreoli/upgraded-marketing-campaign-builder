"""Compatibility shim — event_subscriber has moved to backend.infrastructure.event_subscriber."""
from backend.infrastructure.event_subscriber import *  # noqa: F401, F403
from backend.infrastructure.event_subscriber import EventSubscriber  # noqa: F401
