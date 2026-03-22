"""
Tests for campaign image asset API endpoints.

Covers:
  - POST .../assets/generate — happy path, platform gating, campaign gating,
    RBAC, invalid index, missing prompt
  - GET  .../assets — happy path, filtering, RBAC
"""

import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.models.campaign import (
    Campaign,
    CampaignBrief,
    CampaignContent,
    CampaignStatus,
    ContentPiece,
    ImageAsset,
    ImageBrief,
)
from backend.models.user import CampaignMemberRole, User, UserRole
from backend.models.workspace import WorkspaceRole
from backend.infrastructure.auth import get_current_user
from backend.tests.mock_store import InMemoryCampaignStore

_OWNER = User(id="asset-owner-001", email="owner@test.com", display_name="Owner", roles=[UserRole.CAMPAIGN_BUILDER])
_EDITOR = User(id="asset-editor-001", email="editor@test.com", display_name="Editor", roles=[UserRole.CAMPAIGN_BUILDER])
_VIEWER = User(id="asset-viewer-001", email="viewer@test.com", display_name="Viewer", roles=[UserRole.CAMPAIGN_BUILDER])
_NON_MEMBER = User(id="asset-nonmember-001", email="non@test.com", display_name="NonMember", roles=[UserRole.CAMPAIGN_BUILDER])

TEST_WS_ID = "test-ws-assets"


class InMemoryImageAssetStore:
    """Minimal in-memory ImageAssetStore for testing."""

    def __init__(self):
        self._assets: list[ImageAsset] = []

    async def create(self, asset: ImageAsset) -> ImageAsset:
        self._assets.append(asset)
        return asset

    async def list_by_campaign(self, campaign_id: str) -> list[ImageAsset]:
        return [a for a in self._assets if a.campaign_id == campaign_id]


def _make_store_with_campaign(
    *,
    generate_images: bool = True,
    with_content: bool = True,
    with_image_brief: bool = True,
) -> tuple[InMemoryCampaignStore, Campaign]:
    """Create a store with a workspace + campaign and return both."""
    store = InMemoryCampaignStore()

    from backend.models.workspace import Workspace
    from datetime import datetime, timezone

    store._workspaces[TEST_WS_ID] = Workspace(
        id=TEST_WS_ID,
        name="Test Workspace",
        owner_id=_OWNER.id,
        is_personal=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store._workspace_members[(TEST_WS_ID, _OWNER.id)] = WorkspaceRole.CREATOR.value
    store._workspace_members[(TEST_WS_ID, _EDITOR.id)] = WorkspaceRole.CONTRIBUTOR.value
    store._workspace_members[(TEST_WS_ID, _VIEWER.id)] = WorkspaceRole.VIEWER.value

    brief = CampaignBrief(
        product_or_service="Test Product",
        goal="Test Goal",
        generate_images=generate_images,
    )

    content = None
    if with_content:
        image_brief = ImageBrief(prompt="A beautiful sunset over mountains") if with_image_brief else None
        content = CampaignContent(
            theme="Test Theme",
            tone_of_voice="Professional",
            pieces=[
                ContentPiece(
                    content_type="social_post",
                    channel="instagram",
                    content="Check out our product!",
                    image_brief=image_brief,
                ),
                ContentPiece(
                    content_type="headline",
                    channel="email",
                    content="Amazing Product Launch",
                ),
            ],
        )

    campaign = Campaign(
        brief=brief,
        owner_id=_OWNER.id,
        workspace_id=TEST_WS_ID,
        status=CampaignStatus.CONTENT_APPROVAL,
        content=content,
    )
    store._campaigns[campaign.id] = campaign
    store._members[(campaign.id, _OWNER.id)] = CampaignMemberRole.OWNER.value
    store._members[(campaign.id, _EDITOR.id)] = CampaignMemberRole.EDITOR.value
    store._members[(campaign.id, _VIEWER.id)] = CampaignMemberRole.VIEWER.value

    return store, campaign


@contextmanager
def _as_user(user: User, store: InMemoryCampaignStore, asset_store: InMemoryImageAssetStore):
    """TestClient context with patched stores."""
    store.add_user(user)
    app.dependency_overrides[get_current_user] = lambda: user
    mock_executor = MagicMock()
    mock_executor.dispatch = AsyncMock()
    try:
        with (
            patch("backend.api.campaigns.get_campaign_store", return_value=store),
            patch("backend.apps.api.dependencies.get_campaign_store", return_value=store),
            patch("backend.api.campaign_members.get_campaign_store", return_value=store),
            patch("backend.api.campaign_assets.get_image_asset_store", return_value=asset_store),
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


# ---------------------------------------------------------------------------
# POST .../assets/generate
# ---------------------------------------------------------------------------

class TestGenerateAsset:
    """Tests for POST /api/workspaces/{ws}/campaigns/{cid}/assets/generate."""

    def test_happy_path(self):
        """201 when all conditions are met."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value=b"fake-png-bytes")
        mock_storage = MagicMock()
        mock_storage.upload = AsyncMock(return_value=("campaigns/x/y.png", "https://blob.test/y.png?sas"))

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_image_generation_service", return_value=mock_gen), \
             patch("backend.api.campaign_assets.get_image_storage_service", return_value=mock_storage), \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 201
        data = r.json()
        assert data["campaign_id"] == campaign.id
        assert data["content_piece_index"] == 0
        assert data["prompt"] == "A beautiful sunset over mountains"
        assert data["image_url"] == "https://blob.test/y.png?sas"
        assert data["storage_path"] == "campaigns/x/y.png"
        mock_gen.generate.assert_awaited_once()
        mock_storage.upload.assert_awaited_once()
        assert len(asset_store._assets) == 1

    def test_prompt_override(self):
        """201 with custom prompt when prompt_override is provided."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value=b"fake-png-bytes")
        mock_storage = MagicMock()
        mock_storage.upload = AsyncMock(return_value=("path.png", "https://url.test"))

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_image_generation_service", return_value=mock_gen), \
             patch("backend.api.campaign_assets.get_image_storage_service", return_value=mock_storage), \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0, "prompt_override": "Custom prompt here"},
            )
        assert r.status_code == 201
        assert r.json()["prompt"] == "Custom prompt here"
        mock_gen.generate.assert_awaited_once_with("Custom prompt here", "1024x1024")

    def test_501_when_platform_disabled(self):
        """501 when IMAGE_GENERATION_ENABLED=false."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = False
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 501
        assert "not enabled" in r.json()["detail"].lower()

    def test_400_when_campaign_images_disabled(self):
        """400 when campaign.brief.generate_images=False."""
        store, campaign = _make_store_with_campaign(generate_images=False)
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 400
        assert "not enabled for this campaign" in r.json()["detail"].lower()

    def test_400_index_out_of_range(self):
        """400 when content_piece_index is out of range."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 99},
            )
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"].lower()

    def test_400_negative_index(self):
        """400 when content_piece_index is negative."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": -1},
            )
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"].lower()

    def test_400_no_content(self):
        """400 when campaign has no content pieces."""
        store, campaign = _make_store_with_campaign(with_content=False)
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 400
        assert "no content" in r.json()["detail"].lower()

    def test_400_no_image_brief_no_override(self):
        """400 when piece has no image_brief and no prompt_override is given."""
        store, campaign = _make_store_with_campaign(with_image_brief=True)
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            # Index 1 has no image_brief
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 1},
            )
        assert r.status_code == 400
        assert "no image brief" in r.json()["detail"].lower()

    def test_rbac_viewer_gets_403(self):
        """Viewer (WRITE denied) should get 403."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_VIEWER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 403

    def test_rbac_non_member_gets_404(self):
        """Non-member should get 404."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_NON_MEMBER, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 404

    def test_rbac_editor_allowed(self):
        """Editor (WRITE allowed) should get 201."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()
        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value=b"fake-png-bytes")
        mock_storage = MagicMock()
        mock_storage.upload = AsyncMock(return_value=("path.png", "https://url.test"))

        with _as_user(_EDITOR, store, asset_store) as client, \
             patch("backend.api.campaign_assets.get_image_generation_service", return_value=mock_gen), \
             patch("backend.api.campaign_assets.get_image_storage_service", return_value=mock_storage), \
             patch("backend.api.campaign_assets.get_settings") as mock_settings:
            mock_settings.return_value.image_generation.enabled = True
            r = client.post(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets/generate",
                json={"content_piece_index": 0},
            )
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# GET .../assets
# ---------------------------------------------------------------------------

class TestListAssets:
    """Tests for GET /api/workspaces/{ws}/campaigns/{cid}/assets."""

    def test_happy_path_empty(self):
        """200 with empty list when no assets exist."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets",
            )
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_assets(self):
        """200 with assets when they exist."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        asset = ImageAsset(
            campaign_id=campaign.id,
            content_piece_index=0,
            prompt="A sunset",
            image_url="https://blob.test/img.png",
            storage_path="campaigns/x/img.png",
        )
        asset_store._assets.append(asset)

        with _as_user(_OWNER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets",
            )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == asset.id
        assert items[0]["prompt"] == "A sunset"

    def test_filter_by_content_piece_index(self):
        """Filters assets by content_piece_index query param."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        asset0 = ImageAsset(campaign_id=campaign.id, content_piece_index=0, prompt="Prompt 0")
        asset1 = ImageAsset(campaign_id=campaign.id, content_piece_index=1, prompt="Prompt 1")
        asset_store._assets.extend([asset0, asset1])

        with _as_user(_OWNER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets?content_piece_index=0",
            )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["content_piece_index"] == 0

    def test_rbac_viewer_allowed(self):
        """Viewer (READ allowed) should get 200."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_VIEWER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets",
            )
        assert r.status_code == 200

    def test_rbac_non_member_gets_404(self):
        """Non-member should get 404."""
        store, campaign = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_NON_MEMBER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/{campaign.id}/assets",
            )
        assert r.status_code == 404

    def test_campaign_not_found(self):
        """404 when campaign does not exist."""
        store, _ = _make_store_with_campaign()
        asset_store = InMemoryImageAssetStore()

        with _as_user(_OWNER, store, asset_store) as client:
            r = client.get(
                f"/api/workspaces/{TEST_WS_ID}/campaigns/nonexistent-id/assets",
            )
        assert r.status_code == 404
