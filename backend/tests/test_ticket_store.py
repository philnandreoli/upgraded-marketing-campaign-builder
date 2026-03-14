"""
Tests for the TicketStore abstraction.

Unit tests use InMemoryTicketStore (no external dependencies).
RedisTicketStore connection logic is tested via mocking.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.infrastructure.ticket_store import (
    InMemoryTicketStore,
    RedisTicketStore,
    TicketStore,
    _KEY_PREFIX,
    get_ticket_store,
)


# ---------------------------------------------------------------------------
# InMemoryTicketStore
# ---------------------------------------------------------------------------


class TestInMemoryTicketStore:
    """Unit tests for the dict-backed InMemoryTicketStore."""

    @pytest.fixture
    def store(self):
        return InMemoryTicketStore()

    @pytest.mark.asyncio
    async def test_store_and_consume_returns_user_id(self, store):
        """store() followed by consume() returns the correct user_id."""
        await store.store("ticket-abc", "user-1")
        user_id = await store.consume("ticket-abc")
        assert user_id == "user-1"

    @pytest.mark.asyncio
    async def test_consume_is_single_use(self, store):
        """Second consume() call returns None (single-use guarantee)."""
        await store.store("ticket-abc", "user-1")
        assert await store.consume("ticket-abc") == "user-1"
        assert await store.consume("ticket-abc") is None

    @pytest.mark.asyncio
    async def test_consume_missing_ticket_returns_none(self, store):
        """Consuming a ticket that was never stored returns None."""
        result = await store.consume("nonexistent-ticket")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_expired_ticket_returns_none(self, store):
        """Expired tickets are rejected even if not yet evicted."""
        await store.store("ticket-abc", "user-1", ttl_seconds=1)
        # Manually set expiry in the past
        store._tickets["ticket-abc"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = await store.consume("ticket-abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_expired_ticket_removes_entry(self, store):
        """Expired tickets are removed from the internal dict on consume()."""
        await store.store("ticket-abc", "user-1")
        store._tickets["ticket-abc"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        await store.consume("ticket-abc")
        assert "ticket-abc" not in store._tickets

    @pytest.mark.asyncio
    async def test_custom_ttl_respected(self, store):
        """Ticket stored with ttl_seconds=60 is valid immediately after store."""
        await store.store("ticket-abc", "user-1", ttl_seconds=60)
        user_id = await store.consume("ticket-abc")
        assert user_id == "user-1"

    @pytest.mark.asyncio
    async def test_close_clears_all_tickets(self, store):
        """close() removes all entries from the internal dict."""
        await store.store("t1", "u1")
        await store.store("t2", "u2")
        await store.close()
        assert store._tickets == {}

    def test_evict_expired_removes_stale_entries(self, store):
        """_evict_expired() removes entries past their expiry time."""
        now = datetime.now(timezone.utc)
        store._tickets["old"] = {"user_id": "u1", "expires_at": now - timedelta(seconds=1)}
        store._tickets["fresh"] = {"user_id": "u2", "expires_at": now + timedelta(seconds=30)}
        count = store._evict_expired()
        assert count == 1
        assert "old" not in store._tickets
        assert "fresh" in store._tickets

    def test_evict_expired_returns_zero_when_nothing_to_remove(self, store):
        """_evict_expired() returns 0 when all tickets are still valid."""
        store._tickets["fresh"] = {
            "user_id": "u1",
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=30),
        }
        assert store._evict_expired() == 0

    def test_implements_ticket_store_abc(self, store):
        """InMemoryTicketStore is a concrete implementation of TicketStore."""
        assert isinstance(store, TicketStore)


# ---------------------------------------------------------------------------
# RedisTicketStore
# ---------------------------------------------------------------------------


class TestRedisTicketStore:
    """Unit tests for RedisTicketStore using a mocked Redis client."""

    def _make_settings(self, mode: str = "local") -> MagicMock:
        settings = MagicMock()
        settings.mode = mode
        settings.url = "redis://localhost:6379/0"
        settings.azure_host = "myredis.redis.cache.windows.net"
        settings.azure_port = 6380
        settings.azure_use_ssl = True
        return settings

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.getdel = AsyncMock()
        redis.aclose = AsyncMock()
        return redis

    @pytest.fixture
    def store_with_client(self, mock_redis):
        """RedisTicketStore with the Redis client pre-injected."""
        store = RedisTicketStore(self._make_settings("local"))
        store._redis = mock_redis
        return store, mock_redis

    @pytest.mark.asyncio
    async def test_store_calls_redis_set_with_ttl(self, store_with_client):
        """store() calls redis.set() with the correct key, value, and TTL."""
        store, mock_redis = store_with_client
        await store.store("ticket-xyz", "user-42", ttl_seconds=30)
        key = f"{_KEY_PREFIX}ticket-xyz"
        mock_redis.set.assert_awaited_once_with(
            key,
            json.dumps({"user_id": "user-42"}),
            ex=30,
        )

    @pytest.mark.asyncio
    async def test_consume_calls_redis_getdel(self, store_with_client):
        """consume() calls redis.getdel() with the correct key."""
        store, mock_redis = store_with_client
        mock_redis.getdel.return_value = json.dumps({"user_id": "user-42"})
        user_id = await store.consume("ticket-xyz")
        key = f"{_KEY_PREFIX}ticket-xyz"
        mock_redis.getdel.assert_awaited_once_with(key)
        assert user_id == "user-42"

    @pytest.mark.asyncio
    async def test_consume_missing_ticket_returns_none(self, store_with_client):
        """consume() returns None when Redis returns None (key not found / expired)."""
        store, mock_redis = store_with_client
        mock_redis.getdel.return_value = None
        result = await store.consume("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_consume_is_single_use_via_getdel(self, store_with_client):
        """Second consume() returns None because GETDEL removes the key."""
        store, mock_redis = store_with_client
        # First call returns the value; second call returns None (key already deleted)
        mock_redis.getdel.side_effect = [json.dumps({"user_id": "user-42"}), None]
        assert await store.consume("ticket-xyz") == "user-42"
        assert await store.consume("ticket-xyz") is None

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, store_with_client):
        """close() calls aclose() on the Redis client and resets the reference."""
        store, mock_redis = store_with_client
        await store.close()
        mock_redis.aclose.assert_awaited_once()
        assert store._redis is None

    @pytest.mark.asyncio
    async def test_close_is_idempotent_when_no_client(self):
        """close() is safe to call when the client has not been initialised."""
        store = RedisTicketStore(self._make_settings("local"))
        await store.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_local_mode_uses_from_url(self):
        """In local mode, _get_client() calls redis.asyncio.from_url()."""
        settings = self._make_settings("local")
        store = RedisTicketStore(settings)
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client) as mock_from_url:
            await store.store("t", "u")
            mock_from_url.assert_called_once_with(
                settings.url,
                decode_responses=True,
            )

    @pytest.mark.asyncio
    async def test_azure_mode_uses_redis_with_ssl(self):
        """In azure mode, _get_client() creates a Redis client with SSL and a token."""
        settings = self._make_settings("azure")
        store = RedisTicketStore(settings)
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        mock_token = MagicMock()
        mock_token.token = "fake-azure-token"
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(return_value=mock_token)

        with patch("redis.asyncio.Redis", return_value=mock_client) as mock_redis_cls, \
             patch("azure.identity.aio.DefaultAzureCredential", return_value=mock_credential):
            await store.store("t", "u")
            mock_redis_cls.assert_called_once_with(
                host=settings.azure_host,
                port=settings.azure_port,
                ssl=settings.azure_use_ssl,
                username="",
                password="fake-azure-token",
                decode_responses=True,
            )

    def test_implements_ticket_store_abc(self):
        """RedisTicketStore is a concrete implementation of TicketStore."""
        store = RedisTicketStore(self._make_settings())
        assert isinstance(store, TicketStore)


# ---------------------------------------------------------------------------
# get_ticket_store() singleton
# ---------------------------------------------------------------------------


class TestGetTicketStore:
    """Tests for the get_ticket_store() singleton factory."""

    def setup_method(self):
        """Reset the module-level singleton before each test."""
        import backend.infrastructure.ticket_store as ts_module
        ts_module._ticket_store = None

    def teardown_method(self):
        """Reset the module-level singleton after each test."""
        import backend.infrastructure.ticket_store as ts_module
        ts_module._ticket_store = None

    def test_returns_redis_ticket_store(self):
        """get_ticket_store() returns a RedisTicketStore by default."""
        mock_settings = MagicMock()
        mock_settings.redis.mode = "local"
        mock_settings.redis.url = "redis://localhost:6379/0"

        with patch("backend.infrastructure.ticket_store.get_settings", return_value=mock_settings):
            store = get_ticket_store()
        assert isinstance(store, RedisTicketStore)

    def test_returns_singleton(self):
        """Repeated calls return the same instance."""
        mock_settings = MagicMock()
        mock_settings.redis.mode = "local"
        mock_settings.redis.url = "redis://localhost:6379/0"

        with patch("backend.infrastructure.ticket_store.get_settings", return_value=mock_settings):
            store1 = get_ticket_store()
            store2 = get_ticket_store()
        assert store1 is store2

    def test_in_memory_store_can_be_injected_for_tests(self):
        """InMemoryTicketStore can replace the singleton for test isolation."""
        in_memory = InMemoryTicketStore()
        with patch("backend.infrastructure.ticket_store._ticket_store", in_memory):
            store = get_ticket_store()
        assert store is in_memory
