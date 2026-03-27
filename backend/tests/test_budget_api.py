from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.infrastructure.auth import get_current_user
from backend.main import app
from backend.models.budget import BudgetEntry, BudgetEntryType
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.models.workspace import Workspace, WorkspaceRole
from backend.tests.mock_store import InMemoryCampaignStore

_OWNER = User(
    id="budget-owner-001",
    email="owner@test.com",
    display_name="Owner",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_EDITOR = User(
    id="budget-editor-001",
    email="editor@test.com",
    display_name="Editor",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_VIEWER = User(
    id="budget-viewer-001",
    email="viewer@test.com",
    display_name="Viewer",
    roles=[UserRole.CAMPAIGN_BUILDER],
)
_NON_MEMBER = User(
    id="budget-nonmember-001",
    email="nonmember@test.com",
    display_name="NonMember",
    roles=[UserRole.CAMPAIGN_BUILDER],
)

TEST_WS_ID = "test-ws-budget"


class InMemoryBudgetEntryStore:
    def __init__(self) -> None:
        self._entries: dict[str, BudgetEntry] = {}

    async def create(self, entry: BudgetEntry) -> BudgetEntry:
        self._entries[entry.id] = entry
        return entry

    async def get(self, entry_id: str):
        return self._entries.get(entry_id)

    async def list_by_campaign(self, campaign_id: str, entry_type=None):
        entries = [e for e in self._entries.values() if e.campaign_id == campaign_id]
        if entry_type is not None:
            entries = [e for e in entries if e.entry_type == entry_type]
        return entries

    async def update(self, entry_id: str, **kwargs):
        entry = self._entries.get(entry_id)
        if entry is None:
            raise ValueError("not found")
        entry.amount = kwargs["amount"]
        entry.currency = kwargs["currency"]
        entry.category = kwargs["category"]
        entry.description = kwargs["description"]
        entry.entry_date = kwargs["entry_date"].date()
        entry.updated_at = datetime.utcnow()
        return entry

    async def delete(self, entry_id: str):
        return self._entries.pop(entry_id, None) is not None

    async def get_summary(self, campaign_id: str, *, alert_threshold_pct: float = 0.8):
        entries = [e for e in self._entries.values() if e.campaign_id == campaign_id]
        planned = sum(
            (e.amount for e in entries if e.entry_type == BudgetEntryType.PLANNED),
            Decimal("0.00"),
        )
        actual = sum(
            (e.amount for e in entries if e.entry_type == BudgetEntryType.ACTUAL),
            Decimal("0.00"),
        )
        ratio = float(actual / planned) if planned > 0 else 0.0
        from backend.models.budget import BudgetSummary

        return BudgetSummary(
            campaign_id=campaign_id,
            currency="USD",
            planned_total=planned,
            actual_total=actual,
            variance=(actual - planned).quantize(Decimal("0.01")),
            spent_ratio=ratio,
            alert_threshold_pct=alert_threshold_pct,
            is_alert_triggered=planned > 0 and ratio >= alert_threshold_pct,
        )

    async def get_workspace_overview(self, workspace_id: str, *, alert_threshold_pct: float = 0.8):
        from backend.models.budget import WorkspaceBudgetOverview, WorkspaceBudgetOverviewItem

        by_campaign: dict[str, list[BudgetEntry]] = {}
        for entry in self._entries.values():
            by_campaign.setdefault(entry.campaign_id, []).append(entry)

        items = []
        planned_total = Decimal("0.00")
        actual_total = Decimal("0.00")
        for campaign_id, entries in by_campaign.items():
            planned = sum(
                (e.amount for e in entries if e.entry_type == BudgetEntryType.PLANNED),
                Decimal("0.00"),
            )
            actual = sum(
                (e.amount for e in entries if e.entry_type == BudgetEntryType.ACTUAL),
                Decimal("0.00"),
            )
            summary = await self.get_summary(campaign_id, alert_threshold_pct=alert_threshold_pct)
            planned_total += planned
            actual_total += actual
            items.append(
                WorkspaceBudgetOverviewItem(
                    campaign_id=campaign_id,
                    campaign_name=f"Campaign {campaign_id}",
                    summary=summary,
                )
            )
        return WorkspaceBudgetOverview(
            workspace_id=workspace_id,
            currency="USD",
            campaign_count=len(items),
            planned_total=planned_total,
            actual_total=actual_total,
            variance=(actual_total - planned_total).quantize(Decimal("0.01")),
            spent_ratio=float(actual_total / planned_total) if planned_total > 0 else 0.0,
            items=items,
        )


def _make_store_with_campaign() -> tuple[InMemoryCampaignStore, Campaign]:
    store = InMemoryCampaignStore()
    store._workspaces[TEST_WS_ID] = Workspace(
        id=TEST_WS_ID,
        name="Budget Workspace",
        owner_id=_OWNER.id,
        is_personal=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store._workspace_members[(TEST_WS_ID, _OWNER.id)] = WorkspaceRole.CREATOR.value
    store._workspace_members[(TEST_WS_ID, _EDITOR.id)] = WorkspaceRole.CONTRIBUTOR.value
    store._workspace_members[(TEST_WS_ID, _VIEWER.id)] = WorkspaceRole.VIEWER.value

    campaign = Campaign(
        brief=CampaignBrief(product_or_service="Budget Product", goal="Budget Goal"),
        owner_id=_OWNER.id,
        workspace_id=TEST_WS_ID,
        status=CampaignStatus.STRATEGY,
    )
    store._campaigns[campaign.id] = campaign
    store._members[(campaign.id, _OWNER.id)] = CampaignMemberRole.OWNER.value
    store._members[(campaign.id, _EDITOR.id)] = CampaignMemberRole.EDITOR.value
    store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value
    for u in [_OWNER, _EDITOR, _VIEWER, _NON_MEMBER]:
        store.add_user(u)
    return store, campaign


@contextmanager
def _as_user(user: User, store: InMemoryCampaignStore, budget_store: InMemoryBudgetEntryStore):
    app.dependency_overrides[get_current_user] = lambda: user
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    try:
        with (
            patch("backend.api.campaigns.get_campaign_store", return_value=store),
            patch("backend.apps.api.dependencies.get_campaign_store", return_value=store),
            patch("backend.api.workspaces.get_campaign_store", return_value=store),
            patch("backend.api.campaign_members.get_campaign_store", return_value=store),
            patch("backend.api.budget_entries.get_campaign_store", return_value=store),
            patch("backend.api.budget_entries.get_budget_entry_store", return_value=budget_store),
            patch("backend.application.campaign_workflow_service.get_campaign_store", return_value=store),
            patch("backend.application.campaign_workflow_service._workflow_service", None),
            patch("backend.api.campaigns.get_executor", return_value=mock_executor),
            patch("backend.api.campaign_workflow.get_executor", return_value=mock_executor),
            patch("backend.apps.api.startup.init_db", new_callable=AsyncMock),
            patch("backend.apps.api.startup.close_db", new_callable=AsyncMock),
        ):
            yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_budget_entry_crud_and_summary_and_workspace_overview():
    store, campaign = _make_store_with_campaign()
    budget_store = InMemoryBudgetEntryStore()
    with _as_user(_OWNER, store, budget_store) as client:
        created = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries",
            json={
                "entry_type": "planned",
                "amount": "100.00",
                "currency": "usd",
                "category": "ads",
                "description": "planned ads",
                "entry_date": "2026-01-01",
            },
        )
        assert created.status_code == 201
        entry_id = created.json()["id"]
        assert created.json()["currency"] == "USD"

        created_actual = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries",
            json={
                "entry_type": "actual",
                "amount": "90.00",
                "currency": "USD",
                "entry_date": "2026-01-02",
            },
        )
        assert created_actual.status_code == 201

        listed = client.get(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries?entry_type=planned"
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.patch(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries/{entry_id}",
            json={
                "amount": "120.00",
                "currency": "usd",
                "category": "ads",
                "description": "updated",
                "entry_date": "2026-01-03",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["amount"] == "120.00"

        summary = client.get(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-summary?alert_threshold_pct=0.8"
        )
        assert summary.status_code == 200
        assert summary.json()["planned_total"] == "120.00"
        assert summary.json()["actual_total"] == "90.00"
        assert summary.json()["is_alert_triggered"] is False

        overview = client.get(
            f"/api/workspaces/{TEST_WS_ID}/budget-overview?alert_threshold_pct=0.8"
        )
        assert overview.status_code == 200
        assert overview.json()["workspace_id"] == TEST_WS_ID
        assert overview.json()["campaign_count"] >= 1

        deleted = client.delete(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries/{entry_id}"
        )
        assert deleted.status_code == 204


def test_budget_rbac_write_blocked_for_viewer_and_404_for_non_member():
    store, campaign = _make_store_with_campaign()
    budget_store = InMemoryBudgetEntryStore()
    with _as_user(_VIEWER, store, budget_store) as client:
        forbidden = client.post(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries",
            json={
                "entry_type": "planned",
                "amount": "10.00",
                "currency": "USD",
                "entry_date": "2026-01-01",
            },
        )
        assert forbidden.status_code == 403

    with _as_user(_NON_MEMBER, store, budget_store) as client:
        hidden = client.get(
            f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/budget-entries"
        )
        assert hidden.status_code == 404
