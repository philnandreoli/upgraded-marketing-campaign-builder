"""Workspace persona REST API."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from backend.api.workspaces import WorkspaceAction, _authorize_workspace
from backend.apps.api.schemas.common import PaginationMeta
from backend.apps.api.schemas.personas import (
    CreatePersonaRequest,
    ParsePersonaRequest,
    ParsePersonaResponse,
    PersonaListResponse,
    PersonaResponse,
    UpdatePersonaRequest,
)
from backend.core.rate_limit import limiter
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.llm_service import get_llm_service
from backend.infrastructure.persona_store import get_persona_store
from backend.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["personas"])


def _to_response(persona) -> PersonaResponse:
    return PersonaResponse(
        id=persona.id,
        workspace_id=persona.workspace_id,
        name=persona.name,
        description=persona.description,
        source_text=persona.source_text,
        created_by=persona.created_by,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


_PARSE_SYSTEM_PROMPT = """You are a marketing persona expert. Parse the given freeform persona description into structured fields.
Return a JSON object with exactly these keys, where every value is a plain-text string (NEVER a nested object, array, or dict):
- demographics: age range, gender, location, income, education level — as a readable sentence or comma-separated phrases
- psychographics: personality traits, values, interests, lifestyle — as a readable sentence or comma-separated phrases
- pain_points: key challenges, frustrations, and problems — as a readable sentence or comma-separated phrases
- behaviors: purchasing patterns, media consumption, brand interactions — as a readable sentence or comma-separated phrases
- channels: preferred communication and marketing channels — as a readable sentence or comma-separated phrases

Each value MUST be a single human-readable string, not a JSON object or list.
If information for a field is not present in the description, return an empty string for that field.
Always return valid JSON with all five keys."""


def _flatten_to_text(value: object) -> str:
    """Convert an LLM-returned value to a clean, human-readable string.

    Handles cases where the model returns a dict or list instead of a plain string.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(_flatten_to_text(item) for item in value if item)
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            v_str = _flatten_to_text(v)
            if v_str:
                parts.append(f"{k.replace('_', ' ').title()}: {v_str}")
        return "; ".join(parts)
    return str(value) if value else ""


@router.post("/personas/parse", response_model=ParsePersonaResponse)
@limiter.limit("10/minute")
async def parse_persona(
    workspace_id: str,
    request: Request,
    response: Response,
    body: ParsePersonaRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> ParsePersonaResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, campaign_store)

    messages = [
        {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Parse this persona description into structured fields:\n\n"
                f"Name: {body.name}\n\nDescription: {body.description}"
            ),
        },
    ]

    try:
        raw = await get_llm_service().chat_json(messages, max_tokens=1024)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Persona parse: LLM returned non-JSON response: %r", raw[:200])
            parsed = {}
        return ParsePersonaResponse(
            name=body.name,
            demographics=_flatten_to_text(parsed.get("demographics", "")),
            psychographics=_flatten_to_text(parsed.get("psychographics", "")),
            pain_points=_flatten_to_text(parsed.get("pain_points", "")),
            behaviors=_flatten_to_text(parsed.get("behaviors", "")),
            channels=_flatten_to_text(parsed.get("channels", "")),
        )
    except Exception:
        logger.warning("Persona parse LLM call failed; returning empty structured fields", exc_info=True)
        return ParsePersonaResponse(
            name=body.name,
            demographics="",
            psychographics="",
            pain_points="",
            behaviors="",
            channels="",
        )


@router.post("/personas", status_code=201, response_model=PersonaResponse)
async def create_persona(
    workspace_id: str,
    body: CreatePersonaRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> PersonaResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, campaign_store)

    persona = await get_persona_store().create(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        source_text=body.source_text,
        created_by=user.id,
    )
    return _to_response(persona)


@router.get("/personas", response_model=PersonaListResponse)
async def list_personas(
    workspace_id: str,
    response: Response,
    user: Optional[User] = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PersonaListResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, campaign_store)

    items, total = await get_persona_store().list_by_workspace(
        workspace_id,
        limit=limit,
        offset=offset,
    )
    returned_count = len(items)
    has_more = offset + returned_count < total
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Returned-Count"] = str(returned_count)
    response.headers["X-Has-More"] = str(has_more).lower()
    return PersonaListResponse(
        items=[_to_response(p) for p in items],
        pagination=PaginationMeta(
            total_count=total,
            offset=offset,
            limit=limit,
            returned_count=returned_count,
            has_more=has_more,
        ),
    )


@router.get("/personas/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    workspace_id: str,
    persona_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> PersonaResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, campaign_store)

    persona = await get_persona_store().get(persona_id)
    if persona is None or persona.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Persona not found")
    return _to_response(persona)


@router.patch("/personas/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    workspace_id: str,
    persona_id: str,
    body: UpdatePersonaRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> PersonaResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, campaign_store)

    existing = await get_persona_store().get(persona_id)
    if existing is None or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Persona not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _to_response(existing)

    updated = await get_persona_store().update(
        persona_id,
        name=updates.get("name"),
        description=updates.get("description"),
    )
    return _to_response(updated)


@router.delete("/personas/{persona_id}", status_code=204, response_class=Response)
async def delete_persona(
    workspace_id: str,
    persona_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign_store = get_campaign_store()
    workspace = await campaign_store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, campaign_store)

    existing = await get_persona_store().get(persona_id)
    if existing is None or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Persona not found")

    await get_persona_store().delete(persona_id)
    return Response(status_code=204)
