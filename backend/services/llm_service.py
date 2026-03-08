"""Compatibility shim — llm_service has moved to backend.infrastructure.llm_service."""
from backend.infrastructure.llm_service import *  # noqa: F401, F403
from backend.infrastructure.llm_service import LLMService, get_llm_service  # noqa: F401
