"""
Package entry point — enables ``python -m backend.apps.worker`` to run the worker.

Delegates to the canonical synchronous entry point in
``backend.apps.worker.main``.
"""

from backend.apps.worker.main import main

main()
