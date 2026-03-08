"""
Tests for backend.services.executors.azure_service_bus.AzureServiceBusExecutor.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service_bus_settings(*, namespace: str = "", connection_string: str = "", queue_name: str = "workflow-jobs"):
    sb = MagicMock()
    sb.namespace = namespace
    sb.connection_string = connection_string
    sb.queue_name = queue_name
    return sb


def _make_settings(*, namespace: str = "", connection_string: str = "", queue_name: str = "workflow-jobs"):
    settings = MagicMock()
    settings.service_bus = _make_service_bus_settings(
        namespace=namespace,
        connection_string=connection_string,
        queue_name=queue_name,
    )
    return settings


def _make_mock_sender(*, is_closed: bool = False):
    """Return a MagicMock sender with async send_messages and close."""
    sender = MagicMock()
    sender._is_closed = is_closed
    sender.send_messages = AsyncMock()
    sender.close = AsyncMock()
    return sender


def _make_mock_client(sender):
    """Return a MagicMock ServiceBusClient (get_queue_sender is sync in the real SDK)."""
    client = MagicMock()
    client.get_queue_sender.return_value = sender
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Initialisation tests
# ---------------------------------------------------------------------------


class TestAzureServiceBusExecutorInit:
    def test_namespace_path_uses_default_azure_credential(self):
        """When namespace is set, DefaultAzureCredential and ServiceBusClient are used."""
        mock_sender = _make_mock_sender()
        mock_client = _make_mock_client(mock_sender)
        mock_credential = AsyncMock()
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(namespace="mybus.servicebus.windows.net")),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
            patch("backend.infrastructure.executors.azure_service_bus.DefaultAzureCredential",
                  return_value=mock_credential) as mock_cred_cls,
        ):
            mock_cls.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            executor = AzureServiceBusExecutor()

        mock_cred_cls.assert_called_once()
        mock_cls.assert_called_once_with(
            fully_qualified_namespace="mybus.servicebus.windows.net",
            credential=mock_credential,
        )
        assert executor._queue_name == "workflow-jobs"

    def test_connection_string_path(self):
        """When connection string is set and namespace is not, from_connection_string is used."""
        mock_sender = _make_mock_sender()
        mock_client = _make_mock_client(mock_sender)
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(connection_string="Endpoint=sb://test/;...")),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
        ):
            mock_cls.from_connection_string.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            executor = AzureServiceBusExecutor()

        mock_cls.from_connection_string.assert_called_once_with("Endpoint=sb://test/;...")
        assert executor._credential is None

    def test_namespace_takes_precedence_over_connection_string(self):
        """Namespace auth is used even when both namespace and connection string are provided."""
        mock_sender = _make_mock_sender()
        mock_client = _make_mock_client(mock_sender)
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(
                      namespace="mybus.servicebus.windows.net",
                      connection_string="Endpoint=sb://test/;...",
                  )),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
            patch("backend.infrastructure.executors.azure_service_bus.DefaultAzureCredential"),
        ):
            mock_cls.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            AzureServiceBusExecutor()

        # from_connection_string must NOT be called
        mock_cls.from_connection_string.assert_not_called()
        mock_cls.assert_called_once()

    def test_missing_config_raises_value_error(self):
        """ValueError is raised when neither namespace nor connection string is configured."""
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings()),
            pytest.raises(ValueError, match="AZURE_SERVICE_BUS_NAMESPACE"),
        ):
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            AzureServiceBusExecutor()

    def test_custom_queue_name(self):
        """Custom AZURE_SERVICE_BUS_QUEUE_NAME is respected."""
        mock_sender = _make_mock_sender()
        mock_client = _make_mock_client(mock_sender)
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(
                      connection_string="Endpoint=sb://test/;...",
                      queue_name="my-custom-queue",
                  )),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
        ):
            mock_cls.from_connection_string.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            executor = AzureServiceBusExecutor()

        assert executor._queue_name == "my-custom-queue"


# ---------------------------------------------------------------------------
# Shared executor fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_sender():
    return _make_mock_sender()


@pytest.fixture
def mock_client(mock_sender):
    return _make_mock_client(mock_sender)


@pytest.fixture
def executor(mock_client):
    """An AzureServiceBusExecutor wired to mock_client via connection-string path."""
    with (
        patch("backend.infrastructure.executors.azure_service_bus.get_settings",
              return_value=_make_settings(connection_string="Endpoint=sb://test/;...")),
        patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
    ):
        mock_cls.from_connection_string.return_value = mock_client
        from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
        return AzureServiceBusExecutor()


@pytest.fixture
def job():
    from backend.services.workflow_executor import WorkflowJob
    return WorkflowJob(
        job_id="test-job-id",
        campaign_id="test-campaign-id",
        action="start_pipeline",
    )


# ---------------------------------------------------------------------------
# dispatch() tests
# ---------------------------------------------------------------------------


class TestDispatch:
    async def test_dispatch_sends_message(self, executor, job, mock_sender):
        """dispatch() calls send_messages on the sender exactly once."""
        await executor.dispatch(job)
        mock_sender.send_messages.assert_awaited_once()

    async def test_message_session_id_is_campaign_id(self, executor, job, mock_sender):
        """Message session_id must equal campaign_id for per-campaign ordering."""
        await executor.dispatch(job)
        sent_msg = mock_sender.send_messages.call_args[0][0]
        assert sent_msg.session_id == "test-campaign-id"

    async def test_message_id_is_job_id(self, executor, job, mock_sender):
        """Message message_id must equal job_id for deduplication."""
        await executor.dispatch(job)
        sent_msg = mock_sender.send_messages.call_args[0][0]
        assert sent_msg.message_id == "test-job-id"

    async def test_message_content_type_is_json(self, executor, job, mock_sender):
        """Message content_type must be application/json."""
        await executor.dispatch(job)
        sent_msg = mock_sender.send_messages.call_args[0][0]
        assert sent_msg.content_type == "application/json"

    async def test_message_body_is_valid_json(self, executor, job, mock_sender):
        """Message body must be valid JSON containing job fields."""
        await executor.dispatch(job)
        sent_msg = mock_sender.send_messages.call_args[0][0]
        body_bytes = b"".join(sent_msg.body)
        payload = json.loads(body_bytes)
        assert payload["job_id"] == "test-job-id"
        assert payload["campaign_id"] == "test-campaign-id"
        assert payload["action"] == "start_pipeline"

    async def test_sender_is_reused_across_calls(self, executor, job, mock_client):
        """The sender is created once and reused for subsequent dispatches."""
        await executor.dispatch(job)
        await executor.dispatch(job)
        mock_client.get_queue_sender.assert_called_once()

    async def test_satisfies_workflow_executor_protocol(self, executor):
        """AzureServiceBusExecutor satisfies the WorkflowExecutor Protocol."""
        from backend.services.workflow_executor import WorkflowExecutor
        assert isinstance(executor, WorkflowExecutor)


# ---------------------------------------------------------------------------
# close() tests
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_closes_sender(self, executor, job, mock_sender):
        """close() closes the sender if it was created."""
        await executor.dispatch(job)  # creates the sender
        await executor.close()
        mock_sender.close.assert_awaited_once()

    async def test_close_before_dispatch_is_safe(self, executor, mock_client):
        """close() is safe to call even if dispatch() was never called."""
        await executor.close()
        mock_client.close.assert_awaited_once()

    async def test_close_clears_sender_reference(self, executor, job):
        """After close(), the internal sender reference is set to None."""
        await executor.dispatch(job)
        await executor.close()
        assert executor._sender is None

    async def test_close_with_managed_identity_closes_credential(self):
        """close() calls close() on the DefaultAzureCredential when using namespace auth."""
        mock_credential = AsyncMock()
        mock_sender = _make_mock_sender()
        mock_client = _make_mock_client(mock_sender)
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(namespace="mybus.servicebus.windows.net")),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
            patch("backend.infrastructure.executors.azure_service_bus.DefaultAzureCredential",
                  return_value=mock_credential),
        ):
            mock_cls.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            exec_ = AzureServiceBusExecutor()

        await exec_.close()
        mock_credential.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# health_check() tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_check_returns_true_when_sender_open(self, executor):
        """health_check() returns True when the sender is not closed."""
        result = await executor.health_check()
        assert result is True

    async def test_health_check_returns_false_when_sender_closed(self):
        """health_check() returns False when the sender is closed."""
        closed_sender = _make_mock_sender(is_closed=True)
        mock_client = _make_mock_client(closed_sender)
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(connection_string="Endpoint=sb://test/;...")),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
        ):
            mock_cls.from_connection_string.return_value = mock_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            exec_ = AzureServiceBusExecutor()

        result = await exec_.health_check()
        assert result is False

    async def test_health_check_returns_false_on_exception(self):
        """health_check() returns False when the sender cannot be obtained."""
        failing_client = MagicMock()
        failing_client.get_queue_sender.side_effect = Exception("connection refused")
        failing_client.close = AsyncMock()
        with (
            patch("backend.infrastructure.executors.azure_service_bus.get_settings",
                  return_value=_make_settings(connection_string="Endpoint=sb://test/;...")),
            patch("backend.infrastructure.executors.azure_service_bus.ServiceBusClient") as mock_cls,
        ):
            mock_cls.from_connection_string.return_value = failing_client
            from backend.services.executors.azure_service_bus import AzureServiceBusExecutor
            exec_ = AzureServiceBusExecutor()

        result = await exec_.health_check()
        assert result is False
