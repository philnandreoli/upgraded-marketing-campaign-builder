"""
Tests for the CampaignStore.

Unit tests use the InMemoryCampaignStore (no database required).
Integration tests target the real PostgreSQL-backed CampaignStore and are
skipped automatically when the database is not reachable.
"""

import os
import pytest
from backend.models.campaign import CampaignBrief, CampaignStatus
from backend.models.workspace import WorkspaceRole
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return InMemoryCampaignStore()


@pytest.fixture
def brief():
    return CampaignBrief(
        product_or_service="CloudSync",
        goal="Increase signups",
        budget=10000,
    )


# ---------------------------------------------------------------------------
# Unit tests — async in-memory store
# ---------------------------------------------------------------------------

class TestCampaignStoreUnit:
    @pytest.mark.asyncio
    async def test_create(self, store, brief):
        c = await store.create(brief)
        assert c.id is not None
        assert c.status == CampaignStatus.DRAFT
        assert c.brief.product_or_service == "CloudSync"

    @pytest.mark.asyncio
    async def test_get_existing(self, store, brief):
        c = await store.create(brief)
        fetched = await store.get(c.id)
        assert fetched is not None
        assert fetched.id == c.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        assert await store.get("not-a-real-id") is None

    @pytest.mark.asyncio
    async def test_list_empty(self, store):
        assert await store.list_all() == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, store, brief):
        await store.create(brief)
        await store.create(brief)
        assert len(await store.list_all()) == 2

    @pytest.mark.asyncio
    async def test_update(self, store, brief):
        c = await store.create(brief)
        c.advance_status(CampaignStatus.STRATEGY)
        await store.update(c)
        fetched = await store.get(c.id)
        assert fetched.status == CampaignStatus.STRATEGY

    @pytest.mark.asyncio
    async def test_delete_existing(self, store, brief):
        c = await store.create(brief)
        assert await store.delete(c.id) is True
        assert await store.get(c.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        assert await store.delete("not-a-real-id") is False

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, store, brief):
        c = await store.create(brief)
        await store.delete(c.id)
        assert len(await store.list_all()) == 0

    # ------------------------------------------------------------------
    # Membership tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_with_owner_adds_membership(self, store, brief):
        c = await store.create(brief, owner_id="user-1")
        accessible = await store.list_accessible("user-1")
        assert any(camp.id == c.id for camp in accessible)

    @pytest.mark.asyncio
    async def test_create_without_owner_no_membership(self, store, brief):
        c = await store.create(brief)
        accessible = await store.list_accessible("user-1")
        assert not any(camp.id == c.id for camp in accessible)

    @pytest.mark.asyncio
    async def test_list_accessible_only_returns_members_campaigns(self, store, brief):
        c1 = await store.create(brief, owner_id="user-1")
        c2 = await store.create(brief, owner_id="user-2")
        accessible = await store.list_accessible("user-1")
        ids = [c.id for c in accessible]
        assert c1.id in ids
        assert c2.id not in ids

    @pytest.mark.asyncio
    async def test_list_accessible_admin_sees_all(self, store, brief):
        from backend.models.user import User, UserRole
        store.add_user(User(id="admin-user", roles=[UserRole.ADMIN, UserRole.CAMPAIGN_BUILDER]))
        await store.create(brief, owner_id="user-1")
        await store.create(brief, owner_id="user-2")
        accessible = await store.list_accessible("admin-user")
        assert len(accessible) == 2

    @pytest.mark.asyncio
    async def test_add_member_grants_access(self, store, brief):
        from backend.models.user import CampaignMemberRole
        c = await store.create(brief, owner_id="user-1")
        await store.add_member(c.id, "user-2", CampaignMemberRole.EDITOR)
        accessible = await store.list_accessible("user-2")
        assert any(camp.id == c.id for camp in accessible)

    @pytest.mark.asyncio
    async def test_remove_member_revokes_access(self, store, brief):
        from backend.models.user import CampaignMemberRole
        c = await store.create(brief, owner_id="user-1")
        await store.add_member(c.id, "user-2", CampaignMemberRole.VIEWER)
        removed = await store.remove_member(c.id, "user-2")
        assert removed is True
        accessible = await store.list_accessible("user-2")
        assert not any(camp.id == c.id for camp in accessible)

    @pytest.mark.asyncio
    async def test_remove_member_nonexistent(self, store, brief):
        c = await store.create(brief, owner_id="user-1")
        assert await store.remove_member(c.id, "no-such-user") is False

    @pytest.mark.asyncio
    async def test_delete_removes_memberships(self, store, brief):
        from backend.models.user import CampaignMemberRole
        c = await store.create(brief, owner_id="user-1")
        await store.add_member(c.id, "user-2", CampaignMemberRole.VIEWER)
        await store.delete(c.id)
        # After deletion, neither user should see the campaign
        assert await store.list_accessible("user-1") == []
        assert await store.list_accessible("user-2") == []


# ---------------------------------------------------------------------------
# Workspace unit tests
# ---------------------------------------------------------------------------

class TestWorkspaceUnit:
    @pytest.mark.asyncio
    async def test_create_workspace(self, store):
        ws = await store.create_workspace("My WS", owner_id="user-1")
        assert ws.id is not None
        assert ws.name == "My WS"
        assert ws.owner_id == "user-1"
        assert ws.is_personal is False

    @pytest.mark.asyncio
    async def test_create_workspace_adds_creator_member(self, store):
        ws = await store.create_workspace("My WS", owner_id="user-1")
        role = await store.get_workspace_member_role(ws.id, "user-1")
        assert role == WorkspaceRole.CREATOR

    @pytest.mark.asyncio
    async def test_get_workspace_existing(self, store):
        ws = await store.create_workspace("My WS", owner_id="user-1")
        fetched = await store.get_workspace(ws.id)
        assert fetched is not None
        assert fetched.id == ws.id
        assert fetched.name == "My WS"

    @pytest.mark.asyncio
    async def test_get_workspace_nonexistent(self, store):
        assert await store.get_workspace("no-such-id") is None

    @pytest.mark.asyncio
    async def test_update_workspace_name(self, store):
        ws = await store.create_workspace("Old Name", owner_id="user-1")
        updated = await store.update_workspace(ws.id, name="New Name")
        assert updated.name == "New Name"
        fetched = await store.get_workspace(ws.id)
        assert fetched.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_workspace_description(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        updated = await store.update_workspace(ws.id, description="Some desc")
        assert updated.description == "Some desc"

    @pytest.mark.asyncio
    async def test_update_workspace_nonexistent(self, store):
        with pytest.raises(ValueError):
            await store.update_workspace("no-such-id", name="x")

    @pytest.mark.asyncio
    async def test_delete_workspace(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        assert await store.delete_workspace(ws.id) is True
        assert await store.get_workspace(ws.id) is None

    @pytest.mark.asyncio
    async def test_delete_workspace_nonexistent(self, store):
        assert await store.delete_workspace("no-such-id") is False

    @pytest.mark.asyncio
    async def test_delete_workspace_orphans_campaigns(self, store, brief):
        ws = await store.create_workspace("WS", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws.id)
        assert c.workspace_id == ws.id
        await store.delete_workspace(ws.id)
        orphaned = await store.get(c.id)
        assert orphaned.workspace_id is None

    @pytest.mark.asyncio
    async def test_list_workspaces_member_sees_own(self, store):
        ws1 = await store.create_workspace("WS1", owner_id="user-1")
        ws2 = await store.create_workspace("WS2", owner_id="user-2")
        visible = await store.list_workspaces("user-1")
        ids = [w.id for w in visible]
        assert ws1.id in ids
        assert ws2.id not in ids

    @pytest.mark.asyncio
    async def test_list_workspaces_admin_sees_all(self, store):
        await store.create_workspace("WS1", owner_id="user-1")
        await store.create_workspace("WS2", owner_id="user-2")
        visible = await store.list_workspaces("admin", is_admin=True)
        assert len(visible) == 2

    @pytest.mark.asyncio
    async def test_list_workspace_campaigns(self, store, brief):
        ws = await store.create_workspace("WS", owner_id="user-1")
        c1 = await store.create(brief, workspace_id=ws.id)
        c2 = await store.create(brief)  # no workspace
        campaigns = await store.list_workspace_campaigns(ws.id)
        ids = [c.id for c in campaigns]
        assert c1.id in ids
        assert c2.id not in ids

    @pytest.mark.asyncio
    async def test_get_personal_workspace(self, store):
        ws = await store.create_workspace("Personal", owner_id="user-1", is_personal=True)
        found = await store.get_personal_workspace("user-1")
        assert found is not None
        assert found.id == ws.id

    @pytest.mark.asyncio
    async def test_get_personal_workspace_none(self, store):
        await store.create_workspace("Regular", owner_id="user-1", is_personal=False)
        assert await store.get_personal_workspace("user-1") is None

    @pytest.mark.asyncio
    async def test_create_campaign_with_workspace_id(self, store, brief):
        ws = await store.create_workspace("WS", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws.id)
        assert c.workspace_id == ws.id

    @pytest.mark.asyncio
    async def test_move_campaign(self, store, brief):
        ws1 = await store.create_workspace("WS1", owner_id="user-1")
        ws2 = await store.create_workspace("WS2", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws1.id)
        moved = await store.move_campaign(c.id, ws2.id)
        assert moved.workspace_id == ws2.id
        fetched = await store.get(c.id)
        assert fetched.workspace_id == ws2.id

    @pytest.mark.asyncio
    async def test_move_campaign_orphan(self, store, brief):
        ws = await store.create_workspace("WS", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws.id)
        moved = await store.move_campaign(c.id, None)
        assert moved.workspace_id is None

    @pytest.mark.asyncio
    async def test_move_campaign_nonexistent(self, store):
        with pytest.raises(ValueError):
            await store.move_campaign("no-such-id", None)

    @pytest.mark.asyncio
    async def test_list_accessible_via_workspace_membership(self, store, brief):
        """A user who is a workspace member should see campaigns in that workspace."""
        ws = await store.create_workspace("WS", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws.id)
        # user-2 is not a direct campaign member, but is a workspace member
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        accessible = await store.list_accessible("user-2")
        assert any(camp.id == c.id for camp in accessible)

    @pytest.mark.asyncio
    async def test_list_accessible_no_duplicate_via_both_memberships(self, store, brief):
        """A user with both direct and workspace membership sees the campaign once."""
        from backend.models.user import CampaignMemberRole
        ws = await store.create_workspace("WS", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws.id)
        await store.add_member(c.id, "user-2", CampaignMemberRole.VIEWER)
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        accessible = await store.list_accessible("user-2")
        ids = [camp.id for camp in accessible]
        assert ids.count(c.id) == 1


# ---------------------------------------------------------------------------
# Workspace membership unit tests
# ---------------------------------------------------------------------------

class TestWorkspaceMembershipUnit:
    @pytest.mark.asyncio
    async def test_add_and_get_member_role(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.CONTRIBUTOR)
        role = await store.get_workspace_member_role(ws.id, "user-2")
        assert role == WorkspaceRole.CONTRIBUTOR

    @pytest.mark.asyncio
    async def test_get_member_role_nonexistent(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        assert await store.get_workspace_member_role(ws.id, "nobody") is None

    @pytest.mark.asyncio
    async def test_add_member_idempotent_update(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.CONTRIBUTOR)
        role = await store.get_workspace_member_role(ws.id, "user-2")
        assert role == WorkspaceRole.CONTRIBUTOR

    @pytest.mark.asyncio
    async def test_remove_workspace_member(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        removed = await store.remove_workspace_member(ws.id, "user-2")
        assert removed is True
        assert await store.get_workspace_member_role(ws.id, "user-2") is None

    @pytest.mark.asyncio
    async def test_remove_workspace_member_nonexistent(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        assert await store.remove_workspace_member(ws.id, "nobody") is False

    @pytest.mark.asyncio
    async def test_update_workspace_member_role(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        await store.update_workspace_member_role(ws.id, "user-2", WorkspaceRole.CREATOR)
        role = await store.get_workspace_member_role(ws.id, "user-2")
        assert role == WorkspaceRole.CREATOR

    @pytest.mark.asyncio
    async def test_update_workspace_member_role_nonexistent(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        with pytest.raises(ValueError):
            await store.update_workspace_member_role(ws.id, "nobody", WorkspaceRole.VIEWER)

    @pytest.mark.asyncio
    async def test_list_workspace_members(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.add_workspace_member(ws.id, "user-2", WorkspaceRole.VIEWER)
        members = await store.list_workspace_members(ws.id)
        user_ids = [m.user_id for m in members]
        assert "user-1" in user_ids  # creator added by create_workspace
        assert "user-2" in user_ids

    @pytest.mark.asyncio
    async def test_list_workspace_members_empty(self, store):
        ws = await store.create_workspace("WS", owner_id="user-1")
        await store.remove_workspace_member(ws.id, "user-1")
        members = await store.list_workspace_members(ws.id)
        assert members == []


# ---------------------------------------------------------------------------
# Defense-in-depth authorization tests
# ---------------------------------------------------------------------------

class TestStoreLayerAuthorization:
    """Verify that destructive store operations enforce ownership/role checks
    when an *acting_user_id* is supplied, and remain backward-compatible when
    the parameter is omitted."""

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_owner_succeeds(self, store, brief):
        c = await store.create(brief, owner_id="owner-1")
        result = await store.delete(c.id, acting_user_id="owner-1")
        assert result is True
        assert await store.get(c.id) is None

    @pytest.mark.asyncio
    async def test_delete_non_owner_raises(self, store, brief):
        from backend.models.user import CampaignMemberRole
        c = await store.create(brief, owner_id="owner-1")
        await store.add_member(c.id, "editor-1", CampaignMemberRole.EDITOR)
        with pytest.raises(PermissionError):
            await store.delete(c.id, acting_user_id="editor-1")

    @pytest.mark.asyncio
    async def test_delete_non_member_raises(self, store, brief):
        c = await store.create(brief, owner_id="owner-1")
        with pytest.raises(PermissionError):
            await store.delete(c.id, acting_user_id="stranger")

    @pytest.mark.asyncio
    async def test_delete_no_acting_user_bypasses_check(self, store, brief):
        """Without acting_user_id the legacy path works for any caller."""
        c = await store.create(brief, owner_id="owner-1")
        assert await store.delete(c.id) is True

    # ------------------------------------------------------------------
    # move_campaign
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_move_campaign_admin_succeeds(self, store, brief):
        from backend.models.user import User, UserRole
        store.add_user(User(id="admin-1", roles=[UserRole.ADMIN, UserRole.CAMPAIGN_BUILDER]))
        ws1 = await store.create_workspace("WS1", owner_id="admin-1")
        ws2 = await store.create_workspace("WS2", owner_id="admin-1")
        c = await store.create(brief, workspace_id=ws1.id)
        moved = await store.move_campaign(c.id, ws2.id, acting_user_id="admin-1")
        assert moved.workspace_id == ws2.id

    @pytest.mark.asyncio
    async def test_move_campaign_non_admin_raises(self, store, brief):
        from backend.models.user import User, UserRole
        store.add_user(User(id="builder-1", roles=[UserRole.CAMPAIGN_BUILDER]))
        ws = await store.create_workspace("WS", owner_id="owner-1")
        c = await store.create(brief, workspace_id=ws.id)
        with pytest.raises(PermissionError):
            await store.move_campaign(c.id, None, acting_user_id="builder-1")

    @pytest.mark.asyncio
    async def test_move_campaign_unknown_user_raises(self, store, brief):
        c = await store.create(brief, owner_id="owner-1")
        with pytest.raises(PermissionError):
            await store.move_campaign(c.id, None, acting_user_id="no-such-user")

    @pytest.mark.asyncio
    async def test_move_campaign_no_acting_user_bypasses_check(self, store, brief):
        ws1 = await store.create_workspace("WS1", owner_id="user-1")
        ws2 = await store.create_workspace("WS2", owner_id="user-1")
        c = await store.create(brief, workspace_id=ws1.id)
        moved = await store.move_campaign(c.id, ws2.id)
        assert moved.workspace_id == ws2.id

    # ------------------------------------------------------------------
    # delete_workspace
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_workspace_creator_succeeds(self, store):
        ws = await store.create_workspace("WS", owner_id="creator-1")
        result = await store.delete_workspace(ws.id, acting_user_id="creator-1")
        assert result is True
        assert await store.get_workspace(ws.id) is None

    @pytest.mark.asyncio
    async def test_delete_workspace_admin_succeeds(self, store):
        from backend.models.user import User, UserRole
        store.add_user(User(id="admin-1", roles=[UserRole.ADMIN, UserRole.CAMPAIGN_BUILDER]))
        ws = await store.create_workspace("WS", owner_id="someone-else")
        result = await store.delete_workspace(ws.id, acting_user_id="admin-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_workspace_viewer_raises(self, store):
        ws = await store.create_workspace("WS", owner_id="owner-1")
        await store.add_workspace_member(ws.id, "viewer-1", WorkspaceRole.VIEWER)
        with pytest.raises(PermissionError):
            await store.delete_workspace(ws.id, acting_user_id="viewer-1")

    @pytest.mark.asyncio
    async def test_delete_workspace_non_member_raises(self, store):
        ws = await store.create_workspace("WS", owner_id="owner-1")
        with pytest.raises(PermissionError):
            await store.delete_workspace(ws.id, acting_user_id="stranger")

    @pytest.mark.asyncio
    async def test_delete_workspace_no_acting_user_bypasses_check(self, store):
        ws = await store.create_workspace("WS", owner_id="owner-1")
        assert await store.delete_workspace(ws.id) is True

    # ------------------------------------------------------------------
    # list_accessible — admin status from DB, not from caller flag
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_accessible_unknown_user_not_admin(self, store, brief):
        """A user not in the store should not receive admin-level access."""
        await store.create(brief, owner_id="someone-else")
        accessible = await store.list_accessible("ghost-user")
        assert accessible == []

    @pytest.mark.asyncio
    async def test_list_accessible_non_admin_user_filtered(self, store, brief):
        from backend.models.user import User, UserRole
        store.add_user(User(id="viewer-1", roles=[UserRole.VIEWER]))
        await store.create(brief, owner_id="someone-else")
        # viewer-1 is not a member of any campaign
        accessible = await store.list_accessible("viewer-1")
        assert accessible == []


def _db_available() -> bool:
    """Check whether the PostgreSQL database is reachable."""
    try:
        import asyncio
        from backend.services.database import engine

        async def _ping():
            async with engine.connect() as conn:
                await conn.execute(engine.dialect.statement_compiler(engine.dialect, None).__class__.__new__(engine.dialect.statement_compiler).__class__.__mro__[0].__call__)  # noqa: E501
        # Simpler check: try importing asyncpg and connecting
        import asyncpg  # noqa: F401
        return "DATABASE_URL" in os.environ
    except Exception:
        return False


_skip_no_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — PostgreSQL integration tests skipped",
)


@_skip_no_db
class TestCampaignStoreIntegration:
    """Integration tests against the real PostgreSQL-backed CampaignStore."""

    @pytest.fixture(autouse=True)
    async def _setup_db(self):
        """Initialise DB tables before each test and clean up after."""
        from backend.services import database as db_mod
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from sqlalchemy.pool import NullPool

        # Dispose the module-level engine to clear any tainted connections
        # left over from other test modules (e.g. test_api_routes imports)
        await db_mod.engine.dispose()

        # Create a dedicated engine with NullPool to avoid connection state issues
        test_engine = create_async_engine(db_mod.DATABASE_URL, echo=False, future=True, poolclass=NullPool)
        test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        # Patch the module-level session factory so the store uses our test engine
        original_session = db_mod.async_session
        db_mod.async_session = test_session_factory

        # Create tables
        async with test_engine.begin() as conn:
            await conn.run_sync(db_mod.Base.metadata.create_all)

        yield

        # Cleanup: delete all rows
        async with test_session_factory() as session:
            await session.execute(sa_delete(db_mod.CampaignRow))
            await session.commit()

        await test_engine.dispose()
        db_mod.async_session = original_session

    @pytest.fixture
    def pg_store(self):
        from backend.services.campaign_store import CampaignStore
        return CampaignStore()

    @pytest.mark.asyncio
    async def test_create_and_get(self, pg_store, brief):
        c = await pg_store.create(brief)
        assert c.id is not None
        fetched = await pg_store.get(c.id)
        assert fetched is not None
        assert fetched.brief.product_or_service == "CloudSync"

    @pytest.mark.asyncio
    async def test_list_all(self, pg_store, brief):
        await pg_store.create(brief)
        await pg_store.create(brief)
        items = await pg_store.list_all()
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_update_persists(self, pg_store, brief):
        c = await pg_store.create(brief)
        c.advance_status(CampaignStatus.STRATEGY)
        await pg_store.update(c)
        fetched = await pg_store.get(c.id)
        assert fetched.status == CampaignStatus.STRATEGY

    @pytest.mark.asyncio
    async def test_delete(self, pg_store, brief):
        c = await pg_store.create(brief)
        assert await pg_store.delete(c.id) is True
        assert await pg_store.get(c.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, pg_store):
        assert await pg_store.delete("no-such-id") is False
