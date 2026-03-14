"""Rate-limiting singleton for the API application.

A single :class:`slowapi.Limiter` instance is shared across all route
modules.  The default limit of ``100/minute`` per remote IP applies to
every route unless a tighter per-route limit is declared with
``@limiter.limit(...)`` or a route is explicitly exempted with
``@limiter.exempt``.

Recommended per-endpoint limits (OWASP A04:2021 — Insecure Design):

| Endpoint                        | Limit         |
|---------------------------------|---------------|
| Global API (default)            | 100 req/min   |
| ``POST /api/campaigns``         | 10 req/min    |
| Admin endpoints (``/api/admin``)|  30 req/min   |
| ``POST /api/ws/ticket``         | 30 req/min    |
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

#: Shared rate-limiter instance.  Import this in route modules that need
#: per-endpoint limits and in ``backend.apps.api.main`` to attach the
#: limiter to the application state.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True,
)
