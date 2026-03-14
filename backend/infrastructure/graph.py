"""
Microsoft Graph API helper for searching Microsoft Entra ID (Azure AD) users.

Uses the client credentials (application permissions) flow to acquire a
token for the Graph API and then queries the /users endpoint.

Prerequisites:
  - The app registration must have the ``User.Read.All`` *application*
    permission granted with admin consent.
  - ``AZURE_CLIENT_SECRET`` must be set in the environment / .env.
  - ``OIDC_CLIENT_ID`` and ``OIDC_AUTHORITY`` must already be configured
    for the authentication flow (they are reused here).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# Input validation for OData filter construction.
# Allows alphanumeric characters, spaces, hyphens, periods, underscores, and
# common email/name characters (@). This prevents OData injection while
# supporting typical name and email prefix searches.
_SAFE_SEARCH_PATTERN = re.compile(r"^[a-zA-Z0-9\s.\-@_]+$")
_MAX_SEARCH_LENGTH = 100


class InvalidSearchInputError(ValueError):
    """Raised when the search term fails input validation."""


def _extract_tenant_id(authority: str) -> Optional[str]:
    """Extract the tenant ID from an OIDC authority URL.

    Handles formats such as:
      - https://login.microsoftonline.com/{tenant_id}/v2.0
      - https://login.microsoftonline.com/{tenant_id}
    """
    match = re.search(
        r"login\.microsoftonline\.com/([^/]+?)(?:/v2\.0)?/?$",
        authority,
    )
    if match:
        return match.group(1)
    return None


async def _get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Acquire an access token for Microsoft Graph using client credentials."""
    url = _TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]


async def search_entra_users(
    search: str,
    authority: str,
    client_id: str,
    client_secret: str,
    top: int = 20,
) -> list[dict]:
    """Search Microsoft Entra ID users by display name, mail, or UPN prefix.

    Args:
        search: The search term (matched as a prefix on displayName, mail,
                and userPrincipalName).
        authority: The OIDC authority URL (used to extract the tenant ID).
        client_id: The application (client) ID of the app registration.
        client_secret: The client secret for the app registration.
        top: Maximum number of results to return (default: 20).

    Returns:
        A list of user dicts with keys: id, displayName, mail, userPrincipalName.

    Raises:
        ValueError: If the tenant ID cannot be extracted from the authority URL,
            or if the search term contains invalid characters.
        httpx.HTTPStatusError: If the Graph API returns an error response.
    """
    # Validate and sanitize the search term before constructing OData filters.
    search = search.strip()
    if not search or len(search) > _MAX_SEARCH_LENGTH:
        return []
    if not _SAFE_SEARCH_PATTERN.match(search):
        raise InvalidSearchInputError("Search contains invalid characters")

    tenant_id = _extract_tenant_id(authority)
    if not tenant_id:
        raise ValueError(
            f"Cannot extract tenant ID from OIDC authority URL: {authority!r}. "
            "Ensure OIDC_AUTHORITY is set to a valid Microsoft Entra URL, e.g. "
            "https://login.microsoftonline.com/<tenant-id>/v2.0"
        )

    token = await _get_graph_token(tenant_id, client_id, client_secret)

    # Escape single quotes in the search term for OData filters.
    safe_search = search.replace("'", "''")
    filter_expr = (
        f"startswith(displayName,'{safe_search}') or "
        f"startswith(mail,'{safe_search}') or "
        f"startswith(userPrincipalName,'{safe_search}')"
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GRAPH_BASE}/users",
            params={
                "$filter": filter_expr,
                "$select": "id,displayName,mail,userPrincipalName",
                "$top": top,
                "$count": "true",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "ConsistencyLevel": "eventual",
            },
        )
        response.raise_for_status()
        return response.json().get("value", [])
