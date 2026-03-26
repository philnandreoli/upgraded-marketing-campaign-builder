"""Azure App Configuration bootstrap loader.

Loads runtime configuration from Azure App Configuration using environment
labels, with automatic Key Vault reference resolution via the Azure App
Configuration Provider SDK. Falls back to `.env` file loading (via
pydantic-settings) for local development.

Configuration source precedence
--------------------------------
1. Explicit process environment variables  (always win — ops/emergency overrides)
2. Azure App Configuration values          (primary source in cloud environments)
3. ``.env`` file defaults                  (pydantic-settings fallback, local dev only)

Bootstrap environment variables
---------------------------------
``AZURE_APP_CONFIGURATION_ENDPOINT``
    Endpoint URL of the Azure App Configuration store, e.g.
    ``https://appcs-dev-marketing.azconfig.io``.  When absent the loader is a
    no-op and pydantic-settings falls back to ``.env``.

``APP_ENV``
    Determines the **label** used to select key-value pairs from the store.
    Must match the label strategy used when populating App Configuration (e.g.
    ``dev``, ``test``, ``prod``).  Defaults to ``development`` if unset.

``AZURE_CLIENT_ID``  (optional)
    Client ID of the user-assigned managed identity.  Required when using
    user-assigned managed identity with ``DefaultAzureCredential``.
    Not needed for system-assigned identity or developer credential flows.

Key Vault references
--------------------
Azure App Configuration natively resolves Key Vault references.  No direct
Key Vault SDK calls are required; the provider transparently fetches secrets
when a value stored in App Configuration is a Key Vault reference.
"""

from __future__ import annotations

import logging
import os

from azure.appconfiguration.provider import (
    AzureAppConfigurationKeyVaultOptions,
    SettingSelector,
    load,
)
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

_BOOTSTRAP_ENDPOINT_VAR = "AZURE_APP_CONFIGURATION_ENDPOINT"
_LABEL_SOURCE_VAR = "APP_ENV"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_azure_app_configuration(endpoint: str, label: str) -> dict[str, str]:
    """Load all key-value pairs from Azure App Configuration for *label*.

    Key Vault references are resolved transparently by the Azure App
    Configuration Provider SDK, so callers receive plaintext values without
    any additional Key Vault SDK calls.  Authentication is handled by
    ``DefaultAzureCredential``, which supports Managed Identity in cloud
    environments and developer credentials (Azure CLI / environment variables)
    locally.

    Parameters
    ----------
    endpoint:
        Azure App Configuration endpoint URL.
    label:
        Label filter used to select environment-specific key-value pairs
        (e.g. ``dev``, ``test``, ``prod``).

    Returns
    -------
    dict[str, str]
        Mapping of configuration key → plaintext value for all settings
        returned by the store under the given label.

    Raises
    ------
    RuntimeError
        When the App Configuration store cannot be reached or a Key Vault
        reference cannot be resolved.
    """
    credential = DefaultAzureCredential()

    logger.debug(
        "config: loading from Azure App Configuration (endpoint=%s, label=%s)",
        endpoint,
        label,
    )

    provider = load(
        endpoint=endpoint,
        credential=credential,
        selectors=[SettingSelector(key_filter="*", label_filter=label)],
        key_vault_options=AzureAppConfigurationKeyVaultOptions(credential=credential),
    )

    return {key: (value if value is not None else "") for key, value in provider.items()}


def bootstrap_config() -> None:
    """Bootstrap runtime configuration from Azure App Configuration.

    When ``AZURE_APP_CONFIGURATION_ENDPOINT`` is present in the process
    environment the function loads all key-value pairs for the label matching
    ``APP_ENV`` and injects them into ``os.environ`` so that pydantic-settings
    picks them up transparently.

    When the endpoint variable is absent the function is a no-op, allowing
    local development to continue using ``.env`` files as loaded by
    pydantic-settings.

    Startup is aborted (``SystemExit(1)``) when the endpoint is set but the
    configuration cannot be loaded (missing keys, unresolvable Key Vault
    references, authentication failures).

    Observability
    -------------
    * Logs the config source, active label, and number of injected settings.
    * **Never** logs secret values — only key names at DEBUG level.
    """
    endpoint = os.environ.get(_BOOTSTRAP_ENDPOINT_VAR)
    if not endpoint:
        logger.info(
            "config: %s not set — using .env fallback (local development mode)",
            _BOOTSTRAP_ENDPOINT_VAR,
        )
        return

    # APP_ENV is expected to be set by the container/deployment as a bootstrap
    # variable.  It doubles as the App Configuration label selector.
    label = os.environ.get(_LABEL_SOURCE_VAR, "development")

    logger.info(
        "config: loading from Azure App Configuration (endpoint=%s, label=%s)",
        endpoint,
        label,
    )

    try:
        loaded = load_azure_app_configuration(endpoint, label)
    except Exception as exc:  # noqa: BLE001
        logger.critical(
            "config: failed to load from Azure App Configuration — startup aborted: %s",
            exc,
        )
        raise SystemExit(1) from exc

    injected = 0
    skipped = 0
    for key, value in loaded.items():
        if key in os.environ:
            # Explicit process env vars always win (emergency/ops override path).
            skipped += 1
        else:
            os.environ[key] = value
            injected += 1

    logger.info(
        "config: loaded %d settings from Azure App Configuration "
        "(label=%s, injected=%d, skipped_by_process_env=%d)",
        len(loaded),
        label,
        injected,
        skipped,
    )
