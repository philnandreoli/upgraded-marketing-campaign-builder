"""
JWT authentication for FastAPI routes.

Validates bearer tokens issued by an OIDC provider (e.g. Microsoft Entra).
When AUTH_ENABLED=False (the default) all requests are treated as anonymous
and the user_id is returned as None — useful for local development without
an identity provider configured.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.config import get_settings

logger = logging.getLogger(__name__)

# auto_error=False so that missing tokens don't immediately 401 when auth is
# disabled — we gate the error ourselves in get_current_user.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# ---------------------------------------------------------------------------
# JWKS / discovery cache (module-level, refreshed every hour)
# ---------------------------------------------------------------------------

_jwks_uri: Optional[str] = None
_jwks_cache: dict = {}
_JWKS_TTL = 3600  # seconds


async def _fetch_jwks_uri(authority: str) -> str:
    discovery_url = f"{authority.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        return resp.json()["jwks_uri"]


async def _fetch_jwks(jwks_uri: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_uri, timeout=10)
        resp.raise_for_status()
        return resp.json().get("keys", [])


async def _get_public_keys() -> list[dict]:
    """Return a cached list of JWK public keys from the OIDC provider."""
    global _jwks_uri, _jwks_cache

    settings = get_settings()
    authority = settings.oidc.authority

    now = time.time()
    if (
        _jwks_cache.get("authority") == authority
        and now < _jwks_cache.get("expires_at", 0)
    ):
        return _jwks_cache["keys"]

    if _jwks_uri is None or _jwks_cache.get("authority") != authority:
        _jwks_uri = await _fetch_jwks_uri(authority)

    keys = await _fetch_jwks(_jwks_uri)
    _jwks_cache = {
        "authority": authority,
        "keys": keys,
        "expires_at": now + _JWKS_TTL,
    }
    return keys


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[str]:
    """
    Validate the bearer token and return the user's unique identifier.

    - When AUTH_ENABLED=False: auth is skipped and None is returned.
    - When AUTH_ENABLED=True:  a valid Bearer token is required; raises
      HTTP 401 on failure and HTTP 503 if the OIDC provider is unreachable.

    The returned identifier is the ``oid`` claim (Azure AD object ID) when
    present, otherwise ``sub``.
    """
    settings = get_settings()

    if not settings.oidc.enabled:
        return None  # Auth disabled — local-dev / testing mode

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        keys = await _get_public_keys()

        # PyJWT supports a list of JWKs directly via PyJWKSet / PyJWK.
        # Build a JWKS dict and let PyJWT pick the right key.
        jwks = jwt.PyJWKSet.from_dict({"keys": keys})
        # Decode to get the kid/alg, then look up the signing key.
        signing_key = None
        unverified_header = jwt.get_unverified_header(token)
        for jwk in jwks.keys:
            if jwk.key_id == unverified_header.get("kid"):
                signing_key = jwk.key
                break
        if signing_key is None and jwks.keys:
            signing_key = jwks.keys[0].key

        if signing_key is None:
            raise credentials_exception

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.oidc.client_id,
        )

        # Prefer the Azure AD object ID; fall back to the standard subject.
        user_id: Optional[str] = payload.get("oid") or payload.get("sub")
        if not user_id:
            raise credentials_exception

        return user_id

    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        raise credentials_exception
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise credentials_exception
    except httpx.HTTPError as exc:
        logger.error("Failed to reach OIDC provider: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
