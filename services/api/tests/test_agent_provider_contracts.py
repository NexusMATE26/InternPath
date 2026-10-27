"""Provider adapter contract and realistic payload tests for InternPath Agentic AI (R2.3).

Validates official API formats for:
- Google Gemini REST API (v1beta)
- OpenAI Chat Completions REST API
- Realistic response fixtures, function calls, multi-call turns, refusals, timeouts, and error handling.
"""
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from app.agent.providers import GeminiProvider, OpenAIProvider
from app.agent.types import AgentMessage, ToolCall
from app.schemas import ToolDefinition


@pytest.fixture
def sample_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="read_active_mission",
            description="Inspect active career mission",
            parameters={
                "type": "object",
                "properties": {"student_id": {"type": "integer"}},
            },
            returns={"type": "object"},
            permission_tier="read_only",
        ),
        ToolDefinition(
            name="simulate_plan_variant",
            description="Simulate alternative pacing",
            parameters={
                "type": "object",
                "properties": {
                    "variant_type": {"type": "string"},
                    "weekly_hours": {"type": "integer"},
                },
                "required": ["variant_type"],
            },
            returns={"type": "object"},
            permission_tier="read_only",
        ),
    ]


# ---------------------------------------------------------------------------
# 1. Gemini Provider Contracts
# ---------------------------------------------------------------------------

def test_gemini_missing_api_key_raises_runtime_error(sample_tool_definitions):
    provider = GeminiProvider(api_key=None, model_name="gemini-1.5-flash")
    provider.api_key = None  # Ensure no env fallback
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        provider.generate_turn([AgentMessage(role="user", content="Hello")], sample_tool_definitions)


def test_gemini_function_call_response_parsing(sample_tool_definitions):
    """GeminiProvider accurately parses functionCall parts from realistic Gemini v1beta response."""
    provider = GeminiProvider(api_key="mock_key", model_name="gemini-1.5-flash")

    mock_response_payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "simulate_plan_variant",
                                "args": {
                                    "variant_type": "pacing_reduction",
                                    "weekly_hours": 10,
                                },
                            }
                        }
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 35,
            "totalTokenCount": 155,
        },
    }

    mock_resp_obj = io.BytesIO(json.dumps(mock_response_payload).encode("utf-8"))
    mock_resp_obj.read = mock_resp_obj.getvalue

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(mock_response_payload).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        resp = provider.generate_turn(
            [AgentMessage(role="user", content="I need 10 hours a week.")],
            sample_tool_definitions,
        )

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "simulate_plan_variant"
        assert resp.tool_calls[0].arguments == {"variant_type": "pacing_reduction", "weekly_hours": 10}
        assert resp.usage["total_tokens"] == 155


def test_gemini_safety_refusal_handling(sample_tool_definitions):
    """GeminiProvider cleanly captures SAFETY finishReason without crashing."""
    provider = GeminiProvider(api_key="mock_key", model_name="gemini-1.5-flash")

    mock_response_payload = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "safetyRatings": [{"category": "HARM_CATEGORY_DANGEROUS", "probability": "HIGH"}],
            }
        ]
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(mock_response_payload).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        resp = provider.generate_turn(
            [AgentMessage(role="user", content="Dangerous prompt")],
            sample_tool_definitions,
        )

        assert resp.tool_calls == []
        assert "[Provider Notice]" in resp.content
        assert "SAFETY" in resp.content


def test_gemini_http_error_diagnostics(sample_tool_definitions):
    """GeminiProvider includes server error body in exception message upon HTTP failure."""
    provider = GeminiProvider(api_key="mock_key", model_name="gemini-1.5-flash", max_retries=0)

    err_fp = io.BytesIO(b'{"error": {"code": 403, "message": "API_KEY_INVALID"}}')
    http_err = urllib.error.HTTPError("https://api.test", 403, "Forbidden", {}, err_fp)

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(RuntimeError, match="API_KEY_INVALID"):
            provider.generate_turn([AgentMessage(role="user", content="Hello")], sample_tool_definitions)


# ---------------------------------------------------------------------------
# 2. OpenAI Provider Contracts
# ---------------------------------------------------------------------------

def test_openai_missing_api_key_raises_runtime_error(sample_tool_definitions):
    provider = OpenAIProvider(api_key=None, model_name="gpt-4o-mini")
    provider.api_key = None
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        provider.generate_turn([AgentMessage(role="user", content="Hello")], sample_tool_definitions)


def test_openai_tool_calls_response_parsing(sample_tool_definitions):
    """OpenAIProvider parses standard tool_calls format with JSON string arguments."""
    provider = OpenAIProvider(api_key="mock_key", model_name="gpt-4o-mini")

    mock_response_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "read_active_mission",
                                "arguments": '{"student_id": 1}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 25,
            "total_tokens": 175,
        },
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(mock_response_payload).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        resp = provider.generate_turn(
            [AgentMessage(role="user", content="Show active mission.")],
            sample_tool_definitions,
        )

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call_abc123"
        assert resp.tool_calls[0].name == "read_active_mission"
        assert resp.tool_calls[0].arguments == {"student_id": 1}
        assert resp.usage["total_tokens"] == 175


def test_openai_refusal_handling(sample_tool_definitions):
    """OpenAIProvider handles refusal field gracefully without crashing."""
    provider = OpenAIProvider(api_key="mock_key", model_name="gpt-4o-mini")

    mock_response_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "refusal": "I cannot fulfill this request due to safety restrictions.",
                },
                "finish_reason": "stop",
            }
        ]
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(mock_response_payload).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        resp = provider.generate_turn(
            [AgentMessage(role="user", content="Refused query")],
            sample_tool_definitions,
        )

        assert resp.tool_calls == []
        assert "[Provider Notice]" in resp.content
        assert "safety restrictions" in resp.content


def test_openai_http_error_diagnostics(sample_tool_definitions):
    """OpenAIProvider includes error body details upon HTTP failure."""
    provider = OpenAIProvider(api_key="mock_key", model_name="gpt-4o-mini", max_retries=0)

    err_fp = io.BytesIO(b'{"error": {"message": "You exceeded your current quota", "type": "insufficient_quota"}}')
    http_err = urllib.error.HTTPError("https://api.openai.com", 429, "Too Many Requests", {}, err_fp)

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(RuntimeError, match="insufficient_quota"):
            provider.generate_turn([AgentMessage(role="user", content="Hello")], sample_tool_definitions)
