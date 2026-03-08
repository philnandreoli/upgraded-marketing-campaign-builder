"""Compatibility shim — the canonical API entry-point has moved.

The canonical entry-point is now ``backend.apps.api.main:app``.
This module re-exports ``app`` so that existing deployments and tests
that reference ``backend.main:app`` continue to work unchanged.

Preferred invocation:
    uvicorn backend.apps.api.main:app --reload --port 8000

Legacy invocation (still works via this shim):
    uvicorn backend.main:app --reload --port 8000
"""

from backend.apps.api.main import app  # noqa: F401  re-export

__all__ = ["app"]
