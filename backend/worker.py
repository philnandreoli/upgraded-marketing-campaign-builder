"""
Compatibility shim — the workflow-engine entry point has moved.

The canonical module is ``backend.apps.worker.main``.  This file re-exports
the public symbols so that ``python -m backend.worker`` and any existing
import of ``backend.worker.Worker`` continue to work without change.

Use the canonical path for new code::

    python -m backend.apps.worker.main
"""

from backend.apps.worker.main import Worker, _async_main, main  # noqa: F401

__all__ = ["Worker", "_async_main", "main"]
