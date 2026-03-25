"""Azure App Configuration bootstrap loader.

Loads runtime configuration from Azure App Configuration using environment
labels, with automatic Key Vault reference resolution. Falls back to `.env`
file loading (via pydantic-settings) for local development.

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
"""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlparse

from azure.appconfiguration import AzureAppConfigurationClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)

_BOOTSTRAP_ENDPOINT_VAR = "AZURE_APP_CONFIGURATION_ENDPOINT"
_LABEL_SOURCE_VAR = "APP_ENV"
_KEYVAULT_REF_CONTENT_TYPE_PREFIX = "application/vnd.microsoft.appconfig.keyvaultref"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_keyvault_reference(secret_uri: str, credential: object) -> str:
    """Resolve a Key Vault secret URI to its plaintext value.

    Parameters
    ----------
    secret_uri:
        Full Key Vault secret URI, e.g.
        ``https://myvault.vault.azure.net/secrets/mysecret`` or
        ``https://myvault.vault.azure.net/secrets/mysecret/abc123``.
    credential:
        Azure credential object (typically ``DefaultAzureCredential``).

    Returns
    -------
    str
        The secret's plaintext value.

    Raises
    ------
    ValueError
        When *secret_uri* does not match the expected format.
    RuntimeError
        When the secret cannot be retrieved from Key Vault.
    """
    parsed = urlparse(secret_uri)
    vault_url = f"{parsed.scheme}://{parsed.netloc}"

    # Expect path of the form /secrets/<name>[/<version>]
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2 or path_parts[0] != "secrets":
        raise ValueError(
            f"Unexpected Key Vault secret URI format: {secret_uri!r}. "
            "Expected https://<vault>.vault.azure.net/secrets/<name>[/<version>]."
        )

    secret_name = path_parts[1]
    version = path_parts[2] if len(path_parts) > 2 else None

    with SecretClient(vault_url=vault_url, credential=credential) as client:  # type: ignore[arg-type]
        secret = client.get_secret(secret_name, version=version)
        return secret.value  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_azure_app_configuration(endpoint: str, label: str) -> dict[str, str]:
    """Load all key-value pairs from Azure App Configuration for *label*.

    Key Vault references are resolved transparently so callers receive
    plaintext values.  Authentication is handled by ``DefaultAzureCredential``,
    which supports Managed Identity in cloud environments and developer
    credentials (Azure CLI / environment variables) locally.

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
        When a Key Vault reference cannot be resolved.
    """
    with DefaultAzureCredential() as credential:
        with AzureAppConfigurationClient(base_url=endpoint, credential=credential) as client:
            settings: dict[str, str] = {}
            kv_references: dict[str, str] = {}  # key → Key Vault secret URI

            logger.debug(
                "config: listing settings from Azure App Configuration (endpoint=%s, label=%s)",
                endpoint,
                label,
            )

            for kv in client.list_configuration_settings(label_filter=label):
                content_type = kv.content_type or ""
                if _KEYVAULT_REF_CONTENT_TYPE_PREFIX in content_type:
                    # Key Vault reference — defer resolution to a single credential context
                    ref_data = json.loads(kv.value)
                    kv_references[kv.key] = ref_data["uri"]
                else:
                    settings[kv.key] = kv.value if kv.value is not None else ""

        # Resolve all Key Vault references while the credential context is still open
        for key, secret_uri in kv_references.items():
            try:
                settings[key] = _resolve_keyvault_reference(secret_uri, credential)
                logger.debug("config: resolved Key Vault reference for '%s'", key)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"config: failed to resolve Key Vault reference for '{key}' "
                    f"(uri={secret_uri!r}): {exc}"
                ) from exc

    return settings


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
