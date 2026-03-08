"""Compatibility shim — azure_service_bus executor has moved to backend.infrastructure.executors.azure_service_bus."""
from backend.infrastructure.executors.azure_service_bus import *  # noqa: F401, F403
from backend.infrastructure.executors.azure_service_bus import AzureServiceBusExecutor  # noqa: F401
