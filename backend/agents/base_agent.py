"""
Base agent — abstract class that all campaign agents inherit from.

Each agent has:
- A system prompt defining its role
- Access to the LLM service
- A hook to build the user prompt from a campaign + task
- A `run` method that executes the LLM call and returns an AgentResult
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from backend.models.messages import AgentMessage, AgentResult, AgentTask, AgentType, MessageRole
from backend.services.llm_service import LLMService, get_llm_service
from backend.services.agent_registry import get_agent_ref

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all marketing campaign agents."""

    agent_type: AgentType  # subclasses must set this

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm = llm_service or get_llm_service()

    # ------------------------------------------------------------------
    # Abstract hooks
    # ------------------------------------------------------------------

    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt that defines this agent's role."""

    @abstractmethod
    def build_user_prompt(self, task: AgentTask, campaign_data: dict[str, Any]) -> str:
        """Build the user prompt for the LLM from the task + campaign."""

    @abstractmethod
    def parse_response(self, raw: str, task: AgentTask) -> dict[str, Any]:
        """Parse the raw LLM output into a structured dict for AgentResult.output."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, task: AgentTask, campaign_data: dict[str, Any]) -> AgentResult:
        """Execute the agent: call the LLM and return a structured result."""
        logger.info("Agent %s starting task %s", self.agent_type.value, task.task_id)

        user_prompt = self.build_user_prompt(task, campaign_data)

        try:
            # Prefer the Foundry Agent Operations path when registered
            agent_ref = get_agent_ref(self.agent_type)
            if agent_ref is not None:
                logger.info(
                    "Using Foundry agent '%s' for %s",
                    agent_ref["name"],
                    self.agent_type.value,
                )
                raw_response = await self._llm.chat_json_with_agent(
                    agent_ref["name"],
                    user_prompt,
                )
            else:
                # Fallback: direct LLM call with system prompt in messages
                messages = [
                    {"role": "system", "content": self.system_prompt()},
                    {"role": "user", "content": user_prompt},
                ]
                raw_response = await self._llm.chat_json(messages)

            output = self.parse_response(raw_response, task)

            agent_messages = [
                AgentMessage(role=MessageRole.SYSTEM, agent_type=self.agent_type, content=self.system_prompt()),
                AgentMessage(role=MessageRole.USER, agent_type=self.agent_type, content=user_prompt),
                AgentMessage(role=MessageRole.ASSISTANT, agent_type=self.agent_type, content=raw_response),
            ]

            logger.info("Agent %s completed task %s successfully", self.agent_type.value, task.task_id)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                campaign_id=task.campaign_id,
                success=True,
                output=output,
                messages=agent_messages,
            )

        except Exception as exc:
            logger.exception("Agent %s failed task %s: %s", self.agent_type.value, task.task_id, exc)
            return AgentResult(
                task_id=task.task_id,
                agent_type=self.agent_type,
                campaign_id=task.campaign_id,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json_parse(raw: str) -> dict[str, Any]:
        """Try to parse JSON, stripping markdown fences if present."""
        text = raw.strip()
        if text.startswith("```"):
            # Remove ```json ... ``` wrapping
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
