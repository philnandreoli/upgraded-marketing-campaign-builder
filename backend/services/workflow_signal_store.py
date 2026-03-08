"""Compatibility shim — workflow_signal_store has moved to backend.infrastructure.workflow_signal_store."""
from backend.infrastructure.workflow_signal_store import *  # noqa: F401, F403
from backend.infrastructure.workflow_signal_store import (  # noqa: F401
    SignalType, WorkflowSignalStore, get_workflow_signal_store,
)
