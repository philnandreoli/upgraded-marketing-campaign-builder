"""
Azure AI Projects LLM service — thin wrapper around the azure-ai-projects SDK
configured for Azure AI Foundry with retry logic.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import get_settings

logger = logging.getLogger(__name__)


class LLMService:
    """Manages communication with Azure AI Foundry via azure-ai-projects."""

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.azure_ai_project
        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(
            endpoint=cfg.endpoint,
            credential=self._credential,
        )
        self._client = self._project_client.get_openai_client()
        self._deployment = cfg.deployment_name
        self._agent_settings = settings.agent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a request via the Responses API and return the output text.

        Parameters
        ----------
        messages : list of {"role": ..., "content": ...} dicts
            The first message with role ``system`` (if any) is extracted and
            passed as the ``instructions`` parameter.  The remaining messages
            are passed as ``input``.
        temperature : override for the default agent temperature
        max_tokens : override for the default max tokens
        response_format : optional response format (e.g. {"type": "json_object"})

        Returns
        -------
        The output text of the response.
        """
        # Separate system instructions from the conversation input
        instructions: str | None = None
        input_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system" and instructions is None:
                instructions = msg["content"]
            else:
                input_messages.append({"type": "message", **msg})

        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "input": input_messages,
            "temperature": temperature or self._agent_settings.temperature,
            "max_output_tokens": max_tokens or self._agent_settings.max_tokens,
        }
        if instructions is not None:
            kwargs["instructions"] = instructions
        if response_format is not None:
            kwargs["text"] = {"format": response_format}
            # The Responses API requires the word 'json' in input messages
            # when using json_object format.
            if response_format.get("type") == "json_object":
                input_messages.append(
                    {"type": "message", "role": "developer", "content": "Return your response as JSON."}
                )

        logger.debug(
            "LLM request — model=%s, input_messages=%d, temp=%.2f",
            self._deployment,
            len(input_messages),
            kwargs["temperature"],
        )

        response = await self._client.responses.create(**kwargs)
        content = response.output_text or ""

        logger.debug("LLM response — usage=%s", response.usage)
        return content

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Convenience wrapper that requests JSON output."""
        return await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield tokens/chunks from the Responses API streaming path when available.

        If the SDK/runtime does not expose a streaming iterator, falls back to a
        single non-streaming call and yields one full chunk.
        """
        # Keep message preprocessing aligned with chat()
        instructions: str | None = None
        input_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system" and instructions is None:
                instructions = msg["content"]
            else:
                input_messages.append({"type": "message", **msg})

        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "input": input_messages,
            "temperature": temperature or self._agent_settings.temperature,
            "max_output_tokens": max_tokens or self._agent_settings.max_tokens,
            "stream": True,
        }
        if instructions is not None:
            kwargs["instructions"] = instructions

        try:
            stream = await self._client.responses.create(**kwargs)
            if hasattr(stream, "__aiter__"):
                async for event in stream:
                    chunk = ""
                    try:
                        # Common event shape in newer clients
                        if hasattr(event, "delta") and event.delta is not None:
                            chunk = str(event.delta)
                        elif hasattr(event, "output_text") and event.output_text:
                            chunk = str(event.output_text)
                        elif isinstance(event, dict):
                            chunk = str(event.get("delta") or event.get("output_text") or "")
                    except Exception:
                        chunk = ""
                    if chunk:
                        yield chunk
                return
        except Exception as exc:
            logger.debug("Streaming path unavailable, falling back to non-streaming chat: %s", exc)

        # Fallback path: interface remains streaming-compatible.
        fallback = await self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        if fallback:
            yield fallback

    # ------------------------------------------------------------------
    # Foundry Agent Operations path
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def chat_with_agent(
        self,
        agent_name: str,
        user_content: str,
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a request through a registered Foundry Agent.

        Creates a conversation, invokes ``responses.create`` with the
        ``agent_reference``, and returns the output text.  The agent's
        ``instructions`` (system prompt) are stored server-side in the
        Foundry agent definition, so only the user message is sent here.
        """
        # Enrich the active span with the Foundry agent name so traces can be
        # filtered by agent at the LLM call boundary.
        trace.get_current_span().set_attribute("agent.name", agent_name)

        input_items: list[dict[str, str]] = [
            {"type": "message", "role": "user", "content": user_content},
        ]
        if response_format and response_format.get("type") == "json_object":
            input_items.append(
                {"type": "message", "role": "developer", "content": "Return your response as JSON."}
            )

        # Create a conversation with the user message
        conversation = await self._client.conversations.create(items=input_items)

        kwargs: dict[str, Any] = {
            "conversation": conversation.id,
            "extra_body": {"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        }
        # Note: the "text" / response_format parameter is NOT allowed when an
        # agent reference is specified.  JSON output is enforced through the
        # agent's instructions (system prompt) and the developer message above.

        logger.debug(
            "Agent request — agent=%s, conversation=%s",
            agent_name,
            conversation.id,
        )

        response = await self._client.responses.create(**kwargs)
        content = response.output_text or ""

        # Clean up the conversation
        try:
            await self._client.conversations.delete(conversation_id=conversation.id)
        except Exception:
            logger.debug("Could not delete conversation %s", conversation.id)

        logger.debug("Agent response — usage=%s", response.usage)
        return content

    async def chat_json_with_agent(
        self,
        agent_name: str,
        user_content: str,
    ) -> str:
        """Convenience wrapper: Foundry agent call requesting JSON output."""
        return await self.chat_with_agent(
            agent_name,
            user_content,
            response_format={"type": "json_object"},
        )


    async def close(self) -> None:
        """Clean up the underlying clients and credential."""
        await self._client.close()
        await self._project_client.close()
        await self._credential.close()


# Singleton-ish accessor ------------------------------------------------

_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Return (and lazily create) the global LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
