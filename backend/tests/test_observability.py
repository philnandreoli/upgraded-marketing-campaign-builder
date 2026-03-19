"""
Tests for observability changes:
- Span attributes set in BaseAgent.run()
- Span attribute set in LLMService.chat_with_agent()
- agent_registry helpers: get_agent_version, refresh_agents
- Instruction reconciliation in register_agents()
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from backend.models.messages import AgentTask, AgentType


# ---- Helpers ----------------------------------------------------------------

def _make_task(agent_type: AgentType = AgentType.STRATEGY) -> AgentTask:
    return AgentTask(
        task_id="t-obs-1",
        agent_type=agent_type,
        campaign_id="c-obs-1",
        instruction="",
    )


MINIMAL_STRATEGY_RESPONSE = json.dumps({
    "objectives": ["grow"],
    "target_audience": {},
    "value_proposition": "vp",
    "positioning": "pos",
    "key_messages": ["msg"],
})


# ---- Span attributes in BaseAgent.run() ------------------------------------

class TestBaseAgentSpanAttributes:
    """Verify that BaseAgent.run() enriches the current OTel span."""

    @pytest.mark.asyncio
    async def test_run_sets_agent_type_and_name(self):
        from backend.orchestration.strategy_agent import StrategyAgent

        mock_llm = MagicMock()
        mock_llm.chat_json = AsyncMock(return_value=MINIMAL_STRATEGY_RESPONSE)
        agent = StrategyAgent(llm_service=mock_llm)

        mock_span = MagicMock()

        with (
            patch("backend.orchestration.base_agent.get_agent_ref", return_value=None),
            patch("backend.orchestration.base_agent.get_agent_version", return_value=None),
            patch("backend.orchestration.base_agent.trace") as mock_trace,
        ):
            mock_trace.get_current_span.return_value = mock_span
            await agent.run(_make_task(AgentType.STRATEGY), {"brief": {}})

        mock_span.set_attribute.assert_any_call("agent.type", "strategy")
        mock_span.set_attribute.assert_any_call("agent.name", "StrategyAgent")

    @pytest.mark.asyncio
    async def test_run_sets_campaign_and_task_ids(self):
        from backend.orchestration.strategy_agent import StrategyAgent

        mock_llm = MagicMock()
        mock_llm.chat_json = AsyncMock(return_value=MINIMAL_STRATEGY_RESPONSE)
        agent = StrategyAgent(llm_service=mock_llm)

        mock_span = MagicMock()

        with (
            patch("backend.orchestration.base_agent.get_agent_ref", return_value=None),
            patch("backend.orchestration.base_agent.get_agent_version", return_value=None),
            patch("backend.orchestration.base_agent.trace") as mock_trace,
        ):
            mock_trace.get_current_span.return_value = mock_span
            task = _make_task(AgentType.STRATEGY)
            await agent.run(task, {"brief": {}})

        mock_span.set_attribute.assert_any_call("campaign.id", "c-obs-1")
        mock_span.set_attribute.assert_any_call("task.id", "t-obs-1")
        mock_span.set_attribute.assert_any_call("workflow.stage", "strategy")

    @pytest.mark.asyncio
    async def test_run_sets_foundry_agent_version_when_available(self):
        from backend.orchestration.strategy_agent import StrategyAgent

        mock_llm = MagicMock()
        mock_llm.chat_json_with_agent = AsyncMock(return_value=MINIMAL_STRATEGY_RESPONSE)
        agent = StrategyAgent(llm_service=mock_llm)

        mock_span = MagicMock()

        with (
            patch(
                "backend.orchestration.base_agent.get_agent_ref",
                return_value={"name": "MarketingStrategyAgent", "type": "agent_reference"},
            ),
            patch("backend.orchestration.base_agent.get_agent_version", return_value="3"),
            patch("backend.orchestration.base_agent.trace") as mock_trace,
        ):
            mock_trace.get_current_span.return_value = mock_span
            await agent.run(_make_task(AgentType.STRATEGY), {"brief": {}})

        mock_span.set_attribute.assert_any_call("foundry.agent.version", "3")

    @pytest.mark.asyncio
    async def test_run_omits_foundry_version_when_not_registered(self):
        from backend.orchestration.strategy_agent import StrategyAgent

        mock_llm = MagicMock()
        mock_llm.chat_json = AsyncMock(return_value=MINIMAL_STRATEGY_RESPONSE)
        agent = StrategyAgent(llm_service=mock_llm)

        mock_span = MagicMock()
        set_calls: list[tuple] = []

        def _record_set(k, v):
            set_calls.append((k, v))

        mock_span.set_attribute.side_effect = _record_set

        with (
            patch("backend.orchestration.base_agent.get_agent_ref", return_value=None),
            patch("backend.orchestration.base_agent.get_agent_version", return_value=None),
            patch("backend.orchestration.base_agent.trace") as mock_trace,
        ):
            mock_trace.get_current_span.return_value = mock_span
            await agent.run(_make_task(AgentType.STRATEGY), {"brief": {}})

        attribute_keys = [k for k, _ in set_calls]
        assert "foundry.agent.version" not in attribute_keys

    @pytest.mark.asyncio
    async def test_run_calls_set_attribute_before_llm(self):
        """Span attributes are set before the LLM call so they're visible
        even if the LLM call fails."""
        from backend.orchestration.strategy_agent import StrategyAgent

        mock_llm = MagicMock()
        agent = StrategyAgent(llm_service=mock_llm)

        call_order: list[str] = []
        mock_span = MagicMock()

        def _record_span(k, v):
            call_order.append(f"span:{k}")

        async def _record_llm(*args, **kwargs):
            call_order.append("llm")
            return MINIMAL_STRATEGY_RESPONSE

        mock_span.set_attribute.side_effect = _record_span
        mock_llm.chat_json = _record_llm

        # Mandatory span attributes set unconditionally by base_agent.run()
        MANDATORY_SPAN_ATTRS = {"agent.type", "agent.name", "campaign.id", "task.id", "workflow.stage"}

        with (
            patch("backend.orchestration.base_agent.get_agent_ref", return_value=None),
            patch("backend.orchestration.base_agent.get_agent_version", return_value=None),
            patch("backend.orchestration.base_agent.trace") as mock_trace,
        ):
            mock_trace.get_current_span.return_value = mock_span
            await agent.run(_make_task(AgentType.STRATEGY), {"brief": {}})

        # All mandatory span attributes come before the LLM call
        first_llm = next((i for i, v in enumerate(call_order) if v == "llm"), len(call_order))
        span_attrs_before_llm = {v.removeprefix("span:") for v in call_order[:first_llm] if v.startswith("span:")}
        assert MANDATORY_SPAN_ATTRS.issubset(span_attrs_before_llm)


# ---- Span attribute in LLMService.chat_with_agent() ------------------------

class TestLLMServiceAgentSpanAttribute:
    """Verify that chat_with_agent() sets agent.name on the active span."""

    @pytest.mark.asyncio
    async def test_chat_with_agent_sets_agent_name_span_attribute(self):
        from backend.infrastructure.llm_service import LLMService

        with (
            patch("backend.infrastructure.llm_service.get_settings") as mock_settings,
            patch("backend.infrastructure.llm_service.DefaultAzureCredential"),
            patch("backend.infrastructure.llm_service.AIProjectClient") as mock_project,
        ):
            mock_settings.return_value = MagicMock(
                azure_ai_project=MagicMock(
                    endpoint="https://test.example.com",
                    deployment_name="gpt-4-test",
                ),
                agent=MagicMock(temperature=0.7, max_tokens=4096),
            )
            mock_openai_client = MagicMock()
            mock_project.return_value.get_openai_client.return_value = mock_openai_client
            service = LLMService()

        mock_resp = MagicMock()
        mock_resp.output_text = '{"result": "ok"}'
        mock_resp.usage = MagicMock()

        mock_conv = MagicMock()
        mock_conv.id = "conv-123"
        service._client.conversations = MagicMock()
        service._client.conversations.create = AsyncMock(return_value=mock_conv)
        service._client.conversations.delete = AsyncMock()
        service._client.responses.create = AsyncMock(return_value=mock_resp)

        mock_span = MagicMock()

        with patch("backend.infrastructure.llm_service.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_span
            await service.chat_with_agent("MarketingStrategyAgent", "test prompt")

        mock_span.set_attribute.assert_called_once_with("agent.name", "MarketingStrategyAgent")


# ---- agent_registry helpers ------------------------------------------------

class TestAgentRegistryHelpers:
    """Unit tests for get_agent_version and refresh_agents."""

    def setup_method(self):
        """Reset the registry cache before each test."""
        import backend.infrastructure.agent_registry as reg
        reg._registered_agents = {}

    def teardown_method(self):
        """Restore the registry cache after each test."""
        import backend.infrastructure.agent_registry as reg
        reg._registered_agents = {}

    def test_get_agent_version_returns_none_when_not_registered(self):
        from backend.infrastructure.agent_registry import get_agent_version

        assert get_agent_version(AgentType.STRATEGY) is None

    def test_get_agent_version_returns_version_string(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import get_agent_version

        reg._registered_agents[AgentType.STRATEGY] = {
            "name": "MarketingStrategyAgent",
            "version": 5,
        }
        assert get_agent_version(AgentType.STRATEGY) == "5"

    def test_get_agent_version_returns_none_for_missing_version_key(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import get_agent_version

        reg._registered_agents[AgentType.STRATEGY] = {"name": "MarketingStrategyAgent"}
        assert get_agent_version(AgentType.STRATEGY) is None

    def test_refresh_agents_clears_cache_and_calls_register(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import refresh_agents

        reg._registered_agents[AgentType.STRATEGY] = {
            "name": "MarketingStrategyAgent",
            "version": "1",
        }

        with patch("backend.infrastructure.agent_registry.register_agents") as mock_register:
            refresh_agents()

        # Cache must be empty right before register_agents is called
        mock_register.assert_called_once()

    def test_refresh_agents_clears_old_entries(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import refresh_agents

        reg._registered_agents[AgentType.STRATEGY] = {
            "name": "MarketingStrategyAgent",
            "version": "1",
        }

        with patch("backend.infrastructure.agent_registry.register_agents"):
            refresh_agents()

        # After refresh, old entries are gone (register_agents is mocked and
        # didn't re-populate, so the dict should be empty)
        assert reg._registered_agents == {}


# ---- register_agents instruction reconciliation ----------------------------

class TestRegisterAgentsReconciliation:
    """Verify that register_agents() creates a new version when instructions differ."""

    def setup_method(self):
        import backend.infrastructure.agent_registry as reg
        reg._registered_agents = {}

    def teardown_method(self):
        import backend.infrastructure.agent_registry as reg
        reg._registered_agents = {}

    def test_creates_new_version_when_instructions_changed(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import register_agents

        mock_existing = MagicMock()
        mock_existing.name = "MarketingStrategyAgent"
        mock_existing.version = 1
        mock_existing.definition.instructions = "OLD instructions"

        mock_new_agent = MagicMock()
        mock_new_agent.name = "MarketingStrategyAgent"
        mock_new_agent.version = 2

        mock_agents_client = MagicMock()
        mock_agents_client.get_latest_version.return_value = mock_existing
        mock_agents_client.create_version.return_value = mock_new_agent

        mock_project_client = MagicMock()
        mock_project_client.__enter__ = MagicMock(return_value=mock_project_client)
        mock_project_client.__exit__ = MagicMock(return_value=False)
        mock_project_client.agents = mock_agents_client

        mock_credential = MagicMock()
        mock_credential.__enter__ = MagicMock(return_value=mock_credential)
        mock_credential.__exit__ = MagicMock(return_value=False)

        with (
            patch("backend.infrastructure.agent_registry.get_settings") as mock_settings,
            patch("azure.identity.DefaultAzureCredential", return_value=mock_credential),
            patch("azure.ai.projects.AIProjectClient", return_value=mock_project_client),
            patch("backend.infrastructure.agent_registry._get_agent_instructions", return_value="NEW instructions"),
        ):
            mock_settings.return_value = MagicMock(
                foundry_agents=MagicMock(enabled=True),
                azure_ai_project=MagicMock(endpoint="https://test.example.com", deployment_name="gpt-4"),
            )
            # Only test with STRATEGY to keep it simple
            original_names = reg._AGENT_NAMES.copy()
            reg._AGENT_NAMES = {AgentType.STRATEGY: "MarketingStrategyAgent"}
            try:
                register_agents()
            finally:
                reg._AGENT_NAMES = original_names

        # create_version should have been called for the changed instructions
        mock_agents_client.create_version.assert_called_once()
        assert reg._registered_agents[AgentType.STRATEGY]["version"] == 2

    def test_reuses_existing_when_instructions_unchanged(self):
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import register_agents

        current_instructions = "SAME instructions"

        mock_existing = MagicMock()
        mock_existing.name = "MarketingStrategyAgent"
        mock_existing.version = 1
        mock_existing.definition.instructions = current_instructions

        mock_agents_client = MagicMock()
        mock_agents_client.get_latest_version.return_value = mock_existing

        mock_project_client = MagicMock()
        mock_project_client.__enter__ = MagicMock(return_value=mock_project_client)
        mock_project_client.__exit__ = MagicMock(return_value=False)
        mock_project_client.agents = mock_agents_client

        mock_credential = MagicMock()
        mock_credential.__enter__ = MagicMock(return_value=mock_credential)
        mock_credential.__exit__ = MagicMock(return_value=False)

        with (
            patch("backend.infrastructure.agent_registry.get_settings") as mock_settings,
            patch("azure.identity.DefaultAzureCredential", return_value=mock_credential),
            patch("azure.ai.projects.AIProjectClient", return_value=mock_project_client),
            patch("backend.infrastructure.agent_registry._get_agent_instructions", return_value=current_instructions),
        ):
            mock_settings.return_value = MagicMock(
                foundry_agents=MagicMock(enabled=True),
                azure_ai_project=MagicMock(endpoint="https://test.example.com", deployment_name="gpt-4"),
            )
            original_names = reg._AGENT_NAMES.copy()
            reg._AGENT_NAMES = {AgentType.STRATEGY: "MarketingStrategyAgent"}
            try:
                register_agents()
            finally:
                reg._AGENT_NAMES = original_names

        # create_version should NOT have been called
        mock_agents_client.create_version.assert_not_called()
        assert reg._registered_agents[AgentType.STRATEGY]["version"] == 1

    def test_reuses_existing_when_instructions_differ_only_in_whitespace(self):
        """Leading/trailing whitespace differences must not trigger a new version."""
        import backend.infrastructure.agent_registry as reg
        from backend.infrastructure.agent_registry import register_agents

        stored_instructions = "  SAME instructions  \n"
        current_instructions = "SAME instructions"

        mock_existing = MagicMock()
        mock_existing.name = "MarketingStrategyAgent"
        mock_existing.version = 1
        mock_existing.definition.instructions = stored_instructions

        mock_agents_client = MagicMock()
        mock_agents_client.get_latest_version.return_value = mock_existing

        mock_project_client = MagicMock()
        mock_project_client.__enter__ = MagicMock(return_value=mock_project_client)
        mock_project_client.__exit__ = MagicMock(return_value=False)
        mock_project_client.agents = mock_agents_client

        mock_credential = MagicMock()
        mock_credential.__enter__ = MagicMock(return_value=mock_credential)
        mock_credential.__exit__ = MagicMock(return_value=False)

        with (
            patch("backend.infrastructure.agent_registry.get_settings") as mock_settings,
            patch("azure.identity.DefaultAzureCredential", return_value=mock_credential),
            patch("azure.ai.projects.AIProjectClient", return_value=mock_project_client),
            patch("backend.infrastructure.agent_registry._get_agent_instructions", return_value=current_instructions),
        ):
            mock_settings.return_value = MagicMock(
                foundry_agents=MagicMock(enabled=True),
                azure_ai_project=MagicMock(endpoint="https://test.example.com", deployment_name="gpt-4"),
            )
            original_names = reg._AGENT_NAMES.copy()
            reg._AGENT_NAMES = {AgentType.STRATEGY: "MarketingStrategyAgent"}
            try:
                register_agents()
            finally:
                reg._AGENT_NAMES = original_names

        # Whitespace-only differences should NOT trigger a new version
        mock_agents_client.create_version.assert_not_called()
        assert reg._registered_agents[AgentType.STRATEGY]["version"] == 1
