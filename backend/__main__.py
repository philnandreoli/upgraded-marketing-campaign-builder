"""
Package entry point — enables ``python -m backend`` to run the worker.

Delegates directly to the worker's synchronous entry point.  To run the
worker by its full module path use ``python -m backend.apps.worker.main``.
"""

from backend.apps.worker.main import main

main()
