"""
Tests for the auto-resume startup logic in backend/apps/api/startup.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.campaign import CampaignBrief, CampaignStatus
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_campaign_brief() -> CampaignBrief:
    return CampaignBrief(product_or_service="TestProduct", goal="Test goal")


async def _create_campaign_with_status(store: InMemoryCampaignStore, status: CampaignStatus):
    """Create a campaign and advance it to the given status."""
    c = await store.create(_make_campaign_brief())
    c.status = status
    await store.update(c)
    return c


# ---------------------------------------------------------------------------
# list_by_status — InMemoryCampaignStore
# ---------------------------------------------------------------------------

class TestListByStatus:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self):
        store = InMemoryCampaignStore()
        await store.create(_make_campaign_brief())  # DRAFT
        result = await store.list_by_status([CampaignStatus.CLARIFICATION])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_matching_campaigns(self):
        store = InMemoryCampaignStore()
        c1 = await _create_campaign_with_status(store, CampaignStatus.CLARIFICATION)
        c2 = await _create_campaign_with_status(store, CampaignStatus.CONTENT_APPROVAL)
        await _create_campaign_with_status(store, CampaignStatus.APPROVED)  # should not appear

        result = await store.list_by_status(
            [CampaignStatus.CLARIFICATION, CampaignStatus.CONTENT_APPROVAL]
        )
        ids = {c.id for c in result}
        assert c1.id in ids
        assert c2.id in ids
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_status_list_returns_nothing(self):
        store = InMemoryCampaignStore()
        await _create_campaign_with_status(store, CampaignStatus.CLARIFICATION)
        result = await store.list_by_status([])
        assert result == []

    @pytest.mark.asyncio
    async def test_all_resumable_statuses(self):
        from backend.apps.api.startup import _RESUMABLE_STATUSES

        store = InMemoryCampaignStore()
        created = []
        for status in _RESUMABLE_STATUSES:
            c = await _create_campaign_with_status(store, status)
            created.append(c)

        # DRAFT and terminal statuses should NOT appear
        await store.create(_make_campaign_brief())  # DRAFT
        await _create_campaign_with_status(store, CampaignStatus.APPROVED)

        result = await store.list_by_status(_RESUMABLE_STATUSES)
        assert len(result) == len(_RESUMABLE_STATUSES)


# ---------------------------------------------------------------------------
# _auto_resume_stuck_pipelines
# ---------------------------------------------------------------------------

class TestAutoResumeStuckPipelines:
    @pytest.mark.asyncio
    async def test_dispatches_for_each_stuck_campaign(self):
        from backend.apps.api.startup import _auto_resume_stuck_pipelines

        store = InMemoryCampaignStore()
        c1 = await _create_campaign_with_status(store, CampaignStatus.CLARIFICATION)
        c2 = await _create_campaign_with_status(store, CampaignStatus.CONTENT_APPROVAL)

        mock_executor = MagicMock()
        mock_executor.dispatch = AsyncMock()

        with (
            patch("backend.apps.api.startup.get_campaign_store", return_value=store),
            patch("backend.apps.api.startup.get_executor", return_value=mock_executor),
            patch("backend.apps.api.startup.asyncio.sleep", new=AsyncMock()),
        ):
            await _auto_resume_stuck_pipelines()

        assert mock_executor.dispatch.await_count == 2
        dispatched_ids = {call.args[0].campaign_id for call in mock_executor.dispatch.await_args_list}
        assert c1.id in dispatched_ids
        assert c2.id in dispatched_ids

    @pytest.mark.asyncio
    async def test_no_dispatch_when_no_stuck_campaigns(self):
        from backend.apps.api.startup import _auto_resume_stuck_pipelines

        store = InMemoryCampaignStore()
        await _create_campaign_with_status(store, CampaignStatus.APPROVED)

        mock_executor = MagicMock()
        mock_executor.dispatch = AsyncMock()

        with (
            patch("backend.apps.api.startup.get_campaign_store", return_value=store),
            patch("backend.apps.api.startup.get_executor", return_value=mock_executor),
            patch("backend.apps.api.startup.asyncio.sleep", new=AsyncMock()),
        ):
            await _auto_resume_stuck_pipelines()

        mock_executor.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_uses_resume_pipeline_action(self):
        from backend.apps.api.startup import _auto_resume_stuck_pipelines

        store = InMemoryCampaignStore()
        await _create_campaign_with_status(store, CampaignStatus.CLARIFICATION)

        mock_executor = MagicMock()
        mock_executor.dispatch = AsyncMock()

        with (
            patch("backend.apps.api.startup.get_campaign_store", return_value=store),
            patch("backend.apps.api.startup.get_executor", return_value=mock_executor),
            patch("backend.apps.api.startup.asyncio.sleep", new=AsyncMock()),
        ):
            await _auto_resume_stuck_pipelines()

        job = mock_executor.dispatch.await_args_list[0].args[0]
        assert job.action == "resume_pipeline"

    @pytest.mark.asyncio
    async def test_store_query_failure_is_handled_gracefully(self):
        """A DB error during the query should not propagate and crash the app."""
        from backend.apps.api.startup import _auto_resume_stuck_pipelines

        mock_store = MagicMock()
        mock_store.list_by_status = AsyncMock(side_effect=RuntimeError("DB error"))

        with (
            patch("backend.apps.api.startup.get_campaign_store", return_value=mock_store),
            patch("backend.apps.api.startup.asyncio.sleep", new=AsyncMock()),
        ):
            # Should not raise
            await _auto_resume_stuck_pipelines()

    @pytest.mark.asyncio
    async def test_dispatch_failure_is_handled_gracefully(self):
        """A dispatch error for one campaign should not prevent other dispatches."""
        from backend.apps.api.startup import _auto_resume_stuck_pipelines

        store = InMemoryCampaignStore()
        c1 = await _create_campaign_with_status(store, CampaignStatus.CLARIFICATION)
        c2 = await _create_campaign_with_status(store, CampaignStatus.CONTENT_APPROVAL)

        call_count = 0

        async def _dispatch_with_first_failure(job):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("dispatch error")

        mock_executor = MagicMock()
        mock_executor.dispatch = AsyncMock(side_effect=_dispatch_with_first_failure)

        with (
            patch("backend.apps.api.startup.get_campaign_store", return_value=store),
            patch("backend.apps.api.startup.get_executor", return_value=mock_executor),
            patch("backend.apps.api.startup.asyncio.sleep", new=AsyncMock()),
        ):
            # Should not raise
            await _auto_resume_stuck_pipelines()

        # Both dispatches were attempted despite the first failure
        assert mock_executor.dispatch.await_count == 2


# ---------------------------------------------------------------------------
# make_startup_handler — auto-resume feature flag integration
# ---------------------------------------------------------------------------

class TestMakeStartupHandlerAutoResume:
    @pytest.mark.asyncio
    async def test_auto_resume_scheduled_when_in_process(self):
        """ensure_future is called when executor=in_process and flag is True."""
        from backend.apps.api.startup import make_startup_handler

        mock_settings = MagicMock()
        mock_settings.app.workflow_executor = "in_process"
        mock_settings.app.auto_resume_on_startup = True

        app = MagicMock()

        with (
            patch("backend.apps.api.startup.get_settings", return_value=mock_settings),
            patch("backend.apps.api.startup.init_db", new=AsyncMock()),
            patch("backend.api.websocket.start_ticket_cleanup_task"),
            patch("backend.apps.api.startup.asyncio.ensure_future") as mock_future,
        ):
            handler = make_startup_handler(app)
            await handler()

        mock_future.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_resume_skipped_when_flag_false(self):
        """ensure_future should NOT be called when AUTO_RESUME_ON_STARTUP=false."""
        from backend.apps.api.startup import make_startup_handler

        mock_settings = MagicMock()
        mock_settings.app.workflow_executor = "in_process"
        mock_settings.app.auto_resume_on_startup = False

        app = MagicMock()

        with (
            patch("backend.apps.api.startup.get_settings", return_value=mock_settings),
            patch("backend.apps.api.startup.init_db", new=AsyncMock()),
            patch("backend.api.websocket.start_ticket_cleanup_task"),
            patch("backend.apps.api.startup.asyncio.ensure_future") as mock_future,
        ):
            handler = make_startup_handler(app)
            await handler()

        mock_future.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_resume_skipped_when_not_in_process(self):
        """ensure_future should NOT be called for external executors."""
        from backend.apps.api.startup import make_startup_handler

        mock_settings = MagicMock()
        mock_settings.app.workflow_executor = "azure_service_bus"
        mock_settings.app.auto_resume_on_startup = True
        mock_settings.events.channel_name = "test_channel"

        app = MagicMock()
        app.state = MagicMock()

        with (
            patch("backend.apps.api.startup.get_settings", return_value=mock_settings),
            patch("backend.apps.api.startup.init_db", new=AsyncMock()),
            patch("backend.apps.api.startup.asyncio.ensure_future") as mock_future,
            patch("backend.api.websocket.manager"),
            patch("backend.infrastructure.event_subscriber.EventSubscriber"),
            patch("backend.infrastructure.database.get_connection_dsn", return_value="dsn"),
            patch("backend.infrastructure.database.get_connection_password", return_value=None),
        ):
            handler = make_startup_handler(app)
            # We patch away the EventSubscriber import inside the handler
            with patch.dict("sys.modules", {
                "backend.api.websocket": MagicMock(manager=MagicMock()),
                "backend.infrastructure.event_subscriber": MagicMock(EventSubscriber=MagicMock()),
            }):
                try:
                    await handler()
                except Exception:
                    pass  # EventSubscriber setup may fail in test; that's OK

        mock_future.assert_not_called()
