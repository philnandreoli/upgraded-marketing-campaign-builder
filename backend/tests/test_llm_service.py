"""
Tests for the LLM Service — mocks the Azure AI Projects SDK to verify
request construction, retry logic, and JSON mode.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.llm_service import LLMService


@pytest.fixture
def llm_service():
    """Create an LLMService with a mocked Azure AI Projects client."""
    with (
        patch("backend.services.llm_service.get_settings") as mock_settings,
        patch("backend.services.llm_service.DefaultAzureCredential") as mock_cred,
        patch("backend.services.llm_service.AIProjectClient") as mock_project,
    ):
        mock_settings.return_value = MagicMock(
            azure_ai_project=MagicMock(
                endpoint="https://test.services.ai.azure.com/api/projects/test-project",
                deployment_name="gpt-4-test",
            ),
            agent=MagicMock(
                temperature=0.7,
                max_tokens=4096,
            ),
        )
        # The project client's get_openai_client returns our mock OpenAI client
        mock_openai_client = MagicMock()
        mock_project.return_value.get_openai_client.return_value = mock_openai_client
        service = LLMService()
    return service


def _mock_response(content: str):
    """Build a mock Responses API response."""
    resp = MagicMock()
    resp.output_text = content
    resp.usage = MagicMock(total_tokens=100)
    return resp


class TestLLMServiceChat:
    @pytest.mark.asyncio
    async def test_chat_returns_content(self, llm_service):
        llm_service._client.responses.create = AsyncMock(
            return_value=_mock_response("Hello, world!")
        )
        result = await llm_service.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_chat_passes_model(self, llm_service):
        mock_create = AsyncMock(return_value=_mock_response("ok"))
        llm_service._client.responses.create = mock_create

        await llm_service.chat([{"role": "user", "content": "test"}])

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "gpt-4-test"

    @pytest.mark.asyncio
    async def test_chat_custom_temperature(self, llm_service):
        mock_create = AsyncMock(return_value=_mock_response("ok"))
        llm_service._client.responses.create = mock_create

        await llm_service.chat(
            [{"role": "user", "content": "test"}],
            temperature=0.1,
        )
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_chat_extracts_system_as_instructions(self, llm_service):
        mock_create = AsyncMock(return_value=_mock_response("ok"))
        llm_service._client.responses.create = mock_create

        await llm_service.chat([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ])
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["instructions"] == "You are helpful."
        assert call_kwargs["input"] == [{"type": "message", "role": "user", "content": "Hi"}]

    @pytest.mark.asyncio
    async def test_chat_uses_max_output_tokens(self, llm_service):
        mock_create = AsyncMock(return_value=_mock_response("ok"))
        llm_service._client.responses.create = mock_create

        await llm_service.chat(
            [{"role": "user", "content": "test"}],
            max_tokens=1024,
        )
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["max_output_tokens"] == 1024


class TestLLMServiceChatJSON:
    @pytest.mark.asyncio
    async def test_chat_json_sets_response_format(self, llm_service):
        mock_create = AsyncMock(return_value=_mock_response('{"key": "val"}'))
        llm_service._client.responses.create = mock_create

        result = await llm_service.chat_json([{"role": "user", "content": "json"}])
        assert result == '{"key": "val"}'

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["text"] == {"format": {"type": "json_object"}}

    @pytest.mark.asyncio
    async def test_chat_empty_content_returns_empty(self, llm_service):
        llm_service._client.responses.create = AsyncMock(
            return_value=_mock_response("")
        )
        result = await llm_service.chat([{"role": "user", "content": "test"}])
        assert result == ""


class TestLLMServiceRetry:
    @pytest.mark.asyncio
    async def test_retries_on_failure(self, llm_service):
        """Verify that the service retries on transient errors."""
        mock_create = AsyncMock(
            side_effect=[
                Exception("transient error"),
                _mock_response("recovered"),
            ]
        )
        llm_service._client.responses.create = mock_create

        result = await llm_service.chat([{"role": "user", "content": "test"}])
        assert result == "recovered"
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, llm_service):
        """After 3 failed attempts, the error should propagate."""
        mock_create = AsyncMock(side_effect=Exception("permanent failure"))
        llm_service._client.responses.create = mock_create

        with pytest.raises(Exception, match="permanent failure"):
            await llm_service.chat([{"role": "user", "content": "test"}])

        assert mock_create.call_count == 3
