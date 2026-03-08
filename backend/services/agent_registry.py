"""Compatibility shim — agent_registry has moved to backend.infrastructure.agent_registry."""
from backend.infrastructure.agent_registry import *  # noqa: F401, F403
from backend.infrastructure.agent_registry import (  # noqa: F401
    get_agent_ref, is_agent_registered, register_agents,
)
