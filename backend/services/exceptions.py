"""
Shared service-layer exceptions.

Defined here (rather than in campaign_workflow_service) so that lower-level
modules (e.g. agents) can raise these without creating circular imports.
"""


class WorkflowConflictError(Exception):
    """Raised when a workflow action is not valid for the current campaign status."""
