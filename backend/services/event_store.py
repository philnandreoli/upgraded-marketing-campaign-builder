"""Compatibility shim — event_store has moved to backend.infrastructure.event_store."""
from backend.infrastructure.event_store import *  # noqa: F401, F403
from backend.infrastructure.event_store import EventStore, get_event_store  # noqa: F401
