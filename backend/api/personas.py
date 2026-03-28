"""Workspace persona REST API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from backend.api.workspaces import WorkspaceAction, _authorize_workspace
from backend.apps.api.schemas.common import PaginationMeta
from backend.apps.api.schemas.personas import (
    CreatePersonaRequest,
    PersonaListResponse,
    PersonaResponse,
    UpdatePersonaRequest,
)
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.persona_store import get_persona_store
from backend.models.user import User

router = APIRouter(tags=["personas"])


def _to_response(persona) -> PersonaResponse:
    return PersonaResponse(
        id=persona.id,
        workspace_id=persona.workspace_id,
        name=persona.name,
        description=persona.description,
        created_by=persona.created_by,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
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
