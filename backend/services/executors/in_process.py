"""Compatibility shim — in_process executor has moved to backend.infrastructure.executors.in_process."""
from backend.infrastructure.executors.in_process import *  # noqa: F401, F403
from backend.infrastructure.executors.in_process import InProcessExecutor  # noqa: F401
