"""
Agent Registry — registers marketing agents as AI Foundry Agent versions.

On startup (when ``FOUNDRY_AGENTS_ENABLED=true``), each marketing agent is
registered via ``project_client.agents.create_version()`` with a
``PromptAgentDefinition`` containing its model deployment and system prompt.

If an agent version already exists **and its instructions match** the current
system prompt, it is reused.  If the instructions have changed, a new version
is created automatically.  Agents persist across restarts — nothing is deleted
on shutdown.

Registration refresh model
--------------------------
Agent registration runs once at worker startup.  To pick up prompt or
behaviour changes you must either:

1. **Restart the worker** — ``register_agents()`` runs again on startup and
   will detect instruction changes, creating a new Foundry agent version.
2. **Call ``refresh_agents()`` explicitly** — clears the in-process cache and
   re-runs ``register_agents()``.  Useful when you want to force a refresh
   without restarting the worker (e.g. from an admin endpoint or a management
   script).

In both cases a new Foundry agent version is only created when the system
prompt has actually changed; otherwise the existing version is reused.

References
----------
https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/ai/azure-ai-projects#performing-agent-operations
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import get_settings
from backend.models.messages import AgentType

logger = logging.getLogger(__name__)

# Mapping of AgentType → Foundry agent name
_AGENT_NAMES: dict[AgentType, str] = {
    AgentType.STRATEGY: "MarketingStrategyAgent",
    AgentType.CONTENT_CREATOR: "MarketingContentAgent",
    AgentType.CHANNEL_PLANNER: "MarketingChannelAgent",
    AgentType.ANALYTICS: "MarketingAnalyticsAgent",
    AgentType.REVIEW_QA: "MarketingReviewAgent",
}

# Cache of registered agent metadata: AgentType → {"name": ..., "version": ...}
_registered_agents: dict[AgentType, dict[str, Any]] = {}


def _get_agent_instructions(agent_type: AgentType) -> str:
    """Instantiate the agent class and return its system prompt.

    We import lazily so the registry module stays lightweight and does not
    pull in the full agent tree at import time.
    """
    from backend.orchestration.strategy_agent import StrategyAgent
    from backend.orchestration.content_creator_agent import ContentCreatorAgent
    from backend.orchestration.channel_planner_agent import ChannelPlannerAgent
    from backend.orchestration.analytics_agent import AnalyticsAgent
    from backend.orchestration.review_qa_agent import ReviewQAAgent

    _cls_map = {
        AgentType.STRATEGY: StrategyAgent,
        AgentType.CONTENT_CREATOR: ContentCreatorAgent,
        AgentType.CHANNEL_PLANNER: ChannelPlannerAgent,
        AgentType.ANALYTICS: AnalyticsAgent,
        AgentType.REVIEW_QA: ReviewQAAgent,
    }

    cls = _cls_map[agent_type]
    # We only need the system prompt — pass a dummy LLM service to avoid
    # creating a real client.  system_prompt() doesn't use self._llm.
    instance = cls.__new__(cls)
    return instance.system_prompt()


def register_agents() -> None:
    """Register (or re-use) all marketing agents in AI Foundry.

    Uses the **synchronous** ``AIProjectClient`` because this runs during
    the FastAPI startup lifecycle (outside the async event loop on first
    import / before ``uvicorn`` serves requests).

    For each agent:

    * If the agent **does not exist** in Foundry, a new version is created.
    * If the agent **exists and its instructions match** the current system
      prompt, the existing version is reused.
    * If the agent **exists but its instructions have changed**, a new version
      is created so that Foundry traces reflect the updated behaviour.

    To pick up instruction changes without restarting the worker, call
    :func:`refresh_agents` instead.
    """
    settings = get_settings()
    if not settings.foundry_agents.enabled:
        logger.info("Foundry Agent Operations disabled (FOUNDRY_AGENTS_ENABLED != true)")
        return

    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.identity import DefaultAzureCredential

    cfg = settings.azure_ai_project

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=cfg.endpoint, credential=credential) as project_client,
    ):
        for agent_type, agent_name in _AGENT_NAMES.items():
            instructions = _get_agent_instructions(agent_type)

            try:
                # Try to fetch the latest version of this agent
                existing = project_client.agents.get_latest_version(agent_name=agent_name)

                # Reconcile: check whether the stored instructions still match
                existing_instructions: str | None = None
                try:
                    existing_instructions = existing.definition.instructions
                except AttributeError:
                    # SDK version may not expose definition — log a warning so
                    # operators know that instruction-change detection is skipped.
                    logger.warning(
                        "Foundry agent '%s': cannot read existing instructions from "
                        "SDK response (definition attribute missing).  Reusing "
                        "existing version without instruction comparison.",
                        agent_name,
                    )

                if existing_instructions is not None and existing_instructions.strip() != instructions.strip():
                    # Instructions have changed — create a new version
                    logger.info(
                        "Foundry agent '%s' instructions changed — creating new version",
                        agent_name,
                    )
                    agent = project_client.agents.create_version(
                        agent_name=agent_name,
                        definition=PromptAgentDefinition(
                            model=cfg.deployment_name,
                            instructions=instructions,
                        ),
                    )
                    logger.info(
                        "Created new Foundry agent version '%s' (version=%s)",
                        agent.name,
                        agent.version,
                    )
                    _registered_agents[agent_type] = {
                        "name": agent.name,
                        "version": agent.version,
                    }
                else:
                    logger.info(
                        "Foundry agent '%s' already exists (version=%s) — reusing",
                        agent_name,
                        existing.version,
                    )
                    _registered_agents[agent_type] = {
                        "name": existing.name,
                        "version": existing.version,
                    }
            except Exception:
                # Agent doesn't exist yet — create it
                try:
                    agent = project_client.agents.create_version(
                        agent_name=agent_name,
                        definition=PromptAgentDefinition(
                            model=cfg.deployment_name,
                            instructions=instructions,
                        ),
                    )
                    logger.info(
                        "Registered Foundry agent '%s' (version=%s)",
                        agent.name,
                        agent.version,
                    )
                    _registered_agents[agent_type] = {
                        "name": agent.name,
                        "version": agent.version,
                    }
                except Exception as exc:
                    logger.warning(
                        "Failed to register Foundry agent '%s': %s — "
                        "agent will fall back to direct LLM calls",
                        agent_name,
                        exc,
                    )

    logger.info(
        "Agent registry ready — %d/%d agents registered",
        len(_registered_agents),
        len(_AGENT_NAMES),
    )


def get_agent_ref(agent_type: AgentType) -> dict[str, str] | None:
    """Return the Foundry agent reference for a given agent type, or None."""
    info = _registered_agents.get(agent_type)
    if info is None:
        return None
    return {"name": info["name"], "type": "agent_reference"}


def get_agent_version(agent_type: AgentType) -> str | None:
    """Return the Foundry agent version string for a given agent type, or None.

    The version is set when the agent is registered (or reused) at startup.
    Returns ``None`` when the agent is not registered or Foundry Agent
    Operations are disabled.
    """
    info = _registered_agents.get(agent_type)
    if info is None:
        return None
    version = info.get("version")
    return str(version) if version is not None else None


def is_agent_registered(agent_type: AgentType) -> bool:
    """Check whether a Foundry agent version exists for the given type."""
    return agent_type in _registered_agents


def refresh_agents() -> None:
    """Clear the in-process agent registry cache and re-run registration.

    Use this to force a refresh of Foundry agent versions without restarting
    the worker — for example after updating an agent's system prompt.  New
    Foundry agent versions are created only when the system prompt has
    actually changed.

    **Operational note:** this function is synchronous and may take several
    seconds when connecting to Azure AI Foundry.  Call it from an admin
    endpoint or management script, not from a hot request path.
    """
    global _registered_agents
    logger.info("Refreshing Foundry agent registry (clearing cache and re-registering)")
    _registered_agents = {}
    register_agents()
