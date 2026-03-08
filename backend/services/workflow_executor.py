"""Compatibility shim — workflow_executor has moved to backend.infrastructure.workflow_executor."""
from backend.infrastructure.workflow_executor import *  # noqa: F401, F403
from backend.infrastructure.workflow_executor import (  # noqa: F401
    WorkflowExecutor, WorkflowJob, get_executor,
)
