"""
JWT authentication for FastAPI routes.

Validates bearer tokens issued by an OIDC provider (e.g. Microsoft Entra).
When AUTH_ENABLED=False (the default) all requests are treated as anonymous
and the user_id is returned as None — useful for local development without
an identity provider configured.

When AUTH_ENABLED=True, the authenticated user is also JIT-provisioned in the
database on first login using their OIDC claims (oid/sub, email, name).
The first user to authenticate when the users table is empty is granted the
admin role (bootstrap); all subsequent new users default to viewer.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.user import User, UserRole
from backend.services.database import UserRow, get_db

logger = logging.getLogger(__name__)

# auto_error=False so that missing tokens don't immediately 401 when auth is
# disabled — we gate the error ourselves in get_current_user.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# ---------------------------------------------------------------------------
# JWKS / discovery cache (module-level, refreshed based on configured TTL)
# ---------------------------------------------------------------------------

_jwks_uri: Optional[str] = None
_jwks_cache: dict = {}


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
    ttl = settings.oidc.jwks_cache_ttl

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
        "expires_at": now + ttl,
    }
    return keys


# ---------------------------------------------------------------------------
# JIT user provisioning
# ---------------------------------------------------------------------------

async def _provision_user(
    db: AsyncSession,
    user_id: str,
    email: Optional[str],
    display_name: Optional[str],
) -> UserRow:
    """Create a UserRow for ``user_id`` if one does not already exist.

    The first user provisioned in an empty users table is bootstrapped as
    admin (solving the chicken-and-egg problem).  All subsequent new users
    default to the viewer role.

    Returns the existing or newly-created UserRow.
    """
    result = await db.get(UserRow, user_id)
    if result is not None:
        return result  # User already exists — nothing to do.

    # Determine the role: admin if the table is currently empty, else viewer.
    count_result = await db.execute(select(func.count()).select_from(UserRow))
    user_count = count_result.scalar_one()
    role = "admin" if user_count == 0 else "viewer"

    now = datetime.utcnow()
    new_user = UserRow(
        id=user_id,
        email=email,
        display_name=display_name,
        role=role,
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    logger.info("Provisioned new user %s with role %s", user_id, role)
    return new_user


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Validate the bearer token and return the authenticated User object.

    - When AUTH_ENABLED=False: auth is skipped and None is returned.
    - When AUTH_ENABLED=True:  a valid Bearer token is required; raises
      HTTP 401 on failure and HTTP 503 if the OIDC provider is unreachable.
      On success the user is JIT-provisioned in the database if needed.

    The user's identifier is the ``oid`` claim (Azure AD object ID) when
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
        if signing_key is None:
            raise credentials_exception

        # Accept both the bare client-id and the api:// Application ID URI
        # as valid audiences so tokens acquired with either scope format work.
        valid_audiences = [
            settings.oidc.client_id,
            f"api://{settings.oidc.client_id}",
        ]

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=valid_audiences,
        )

        # Prefer the Azure AD object ID; fall back to the standard subject.
        user_id: Optional[str] = payload.get("oid") or payload.get("sub")
        if not user_id:
            raise credentials_exception

        # JIT-provision the user from JWT claims if this is their first login.
        email: Optional[str] = payload.get("preferred_username") or payload.get("email")
        display_name: Optional[str] = payload.get("name")
        user_row = await _provision_user(db, user_id, email, display_name)

        return User(
            id=user_row.id,
            email=user_row.email,
            display_name=user_row.display_name,
            role=UserRole(user_row.role),
            created_at=user_row.created_at,
            updated_at=user_row.updated_at,
            is_active=user_row.is_active,
        )

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


# ---------------------------------------------------------------------------
# Convenience dependencies
# ---------------------------------------------------------------------------


async def require_authenticated(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Raise 401 if auth is disabled (user is None) or token is missing."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_campaign_builder(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Raise 403 if the user has viewer role (cannot build campaigns)."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


async def require_admin(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Raise 403 if the user is not an admin."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user
