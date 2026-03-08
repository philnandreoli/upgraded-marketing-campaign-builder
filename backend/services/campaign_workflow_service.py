"""Compatibility shim — campaign_workflow_service has moved to backend.application.campaign_workflow_service."""
from backend.application.campaign_workflow_service import *  # noqa: F401, F403
from backend.application.campaign_workflow_service import (  # noqa: F401
    CampaignWorkflowService, WorkflowConflictError, get_workflow_service,
)
