"""Provider-compatible tool-calling adapters for InternPath Agentic AI (R2.2).

Supports:
- GeminiProvider: Official Google Gemini REST API v1beta with function calling
- OpenAIProvider: Official OpenAI Chat Completions REST API with tool calling
- MockProvider: Deterministic, scriptable mock provider for test suites
- BaseLLMProvider: Abstract interface defining normalized turn generation
"""
import abc
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Optional

from app.agent.types import AgentMessage, ModelTurnResponse, ToolCall
from app.schemas import ToolDefinition

logger = logging.getLogger("internpath.agent.providers")


class BaseLLMProvider(abc.ABC):
    """Abstract base class for provider-compatible function/tool-calling adapters."""

    def __init__(self, model_name: str, timeout_seconds: float = 10.0, max_retries: int = 2):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @abc.abstractmethod
    def get_engine_label(self) -> str:
        """Truthful engine label for audit logging (e.g. gemini:gemini-1.5-flash, mock_llm)."""
        pass

    @abc.abstractmethod
    def is_live_provider(self) -> bool:
        """True if backed by live network API keys and verified live service."""
        pass

    @abc.abstractmethod
    def generate_turn(
        self,
        messages: list[AgentMessage],
        tool_definitions: list[ToolDefinition],
        timeout_seconds: Optional[float] = None,
    ) -> ModelTurnResponse:
        """Execute one conversational generation turn, returning text or tool calls."""
        pass


class GeminiProvider(BaseLLMProvider):
    """Google Gemini REST API adapter supporting official function calling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
    ):
        model = model_name or os.environ.get("INTERNPATH_LLM_MODEL") or "gemini-1.5-flash"
        super().__init__(model_name=model, timeout_seconds=timeout_seconds, max_retries=max_retries)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def get_engine_label(self) -> str:
        return f"gemini:{self.model_name}"

    def is_live_provider(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("fake_") and not self.api_key.startswith("mock_"))

    def _format_gemini_contents(self, messages: list[AgentMessage]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                # System message in Gemini contents is represented as initial user or systemInstruction
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"[System Instructions]\n{msg.content}"}],
                })
            elif msg.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg.content or ""}],
                })
            elif msg.role == "assistant":
                parts: list[dict[str, Any]] = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append({
                            "functionCall": {
                                "name": tc.name,
                                "args": tc.arguments,
                            }
                        })
                if msg.content:
                    parts.append({"text": msg.content})
                contents.append({
                    "role": "model",
                    "parts": parts if parts else [{"text": ""}],
                })
            elif msg.role == "tool":
                # In Gemini v1beta, function execution outputs are returned in role 'function'
                tool_output = msg.content
                if isinstance(tool_output, str):
                    try:
                        tool_output = json.loads(tool_output)
                    except Exception:
                        tool_output = {"result": tool_output}
                elif not isinstance(tool_output, dict):
                    tool_output = {"result": tool_output}

                contents.append({
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.name or "tool",
                                "response": tool_output,
                            }
                        }
                    ],
                })

        return contents

    def _format_gemini_tools(self, tool_definitions: list[ToolDefinition]) -> list[dict[str, Any]]:
        def normalize_schema(schema: Any) -> Any:
            if isinstance(schema, dict):
                normalized: dict[str, Any] = {}
                for k, v in schema.items():
                    if k == "type" and isinstance(v, str):
                        normalized["type"] = v.upper()
                    elif k in ("properties", "patternProperties") and isinstance(v, dict):
                        normalized[k] = {prop_k: normalize_schema(prop_v) for prop_k, prop_v in v.items()}
                    elif k == "items":
                        normalized["items"] = normalize_schema(v)
                    else:
                        normalized[k] = normalize_schema(v) if isinstance(v, (dict, list)) else v
                return normalized
            elif isinstance(schema, list):
                return [normalize_schema(item) for item in schema]
            return schema

        declarations = []
        for td in tool_definitions:
            params = normalize_schema(td.parameters) if td.parameters else {"type": "OBJECT", "properties": {}}
            declarations.append({
                "name": td.name,
                "description": td.description,
                "parameters": params,
            })
        # Support both snake_case and camelCase keys for official Gemini REST compatibility
        return [{"function_declarations": declarations, "functionDeclarations": declarations}]

    def generate_turn(
        self,
        messages: list[AgentMessage],
        tool_definitions: list[ToolDefinition],
        timeout_seconds: Optional[float] = None,
    ) -> ModelTurnResponse:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured for live GeminiProvider.")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.api_key}"
        )

        body: dict[str, Any] = {
            "contents": self._format_gemini_contents(messages),
            "generationConfig": {
                "temperature": 0.1,
            },
        }

        if tool_definitions:
            body["tools"] = self._format_gemini_tools(tool_definitions)

        timeout = timeout_seconds or self.timeout_seconds
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        return ModelTurnResponse(content="", tool_calls=[], raw_response=resp_data)

                    first_candidate = candidates[0]
                    finish_reason = first_candidate.get("finishReason")
                    if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST"):
                        logger.warning("Gemini candidate blocked by safety filter: %s", finish_reason)
                        return ModelTurnResponse(
                            content=f"[Provider Notice] Generation blocked by provider safety policy: {finish_reason}",
                            tool_calls=[],
                            raw_response=resp_data,
                        )

                    content_obj = first_candidate.get("content", {})
                    parts = content_obj.get("parts", [])

                    tool_calls: list[ToolCall] = []
                    text_parts: list[str] = []

                    for part in parts:
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls.append(
                                ToolCall(
                                    id=f"call_{uuid.uuid4().hex[:8]}",
                                    name=fc.get("name", ""),
                                    arguments=fc.get("args", {}),
                                )
                            )
                        elif "text" in part:
                            text_parts.append(part["text"])

                    usage = resp_data.get("usageMetadata", {})
                    token_usage = {
                        "prompt_tokens": usage.get("promptTokenCount", 0),
                        "completion_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0),
                    }

                    combined_text = "\n".join(text_parts).strip() if text_parts else None
                    return ModelTurnResponse(
                        content=combined_text,
                        tool_calls=tool_calls,
                        usage=token_usage,
                        raw_response=resp_data,
                    )
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                err_detail = ""
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        err_detail = f": {exc.read().decode('utf-8')}"
                    except Exception:
                        pass
                last_error = f"{exc}{err_detail}"
                logger.warning("Gemini API call attempt %d failed: %s", attempt + 1, last_error)
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"Gemini API request failed after {self.max_retries + 1} attempts: {last_error}")


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Chat Completions REST API adapter supporting official tool calling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
    ):
        model = model_name or os.environ.get("INTERNPATH_LLM_MODEL") or "gpt-4o-mini"
        super().__init__(model_name=model, timeout_seconds=timeout_seconds, max_retries=max_retries)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def get_engine_label(self) -> str:
        return f"openai:{self.model_name}"

    def is_live_provider(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("fake_") and not self.api_key.startswith("mock_"))

    def _format_openai_messages(self, messages: list[AgentMessage]) -> list[dict[str, Any]]:
        openai_msgs: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                openai_msgs.append({"role": "system", "content": msg.content or ""})
            elif msg.role == "user":
                openai_msgs.append({"role": "user", "content": msg.content or ""})
            elif msg.role == "assistant":
                item: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    item["content"] = msg.content
                if msg.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                openai_msgs.append(item)
            elif msg.role == "tool":
                content_str = (
                    json.dumps(msg.content)
                    if not isinstance(msg.content, str)
                    else msg.content
                )
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or f"call_{uuid.uuid4().hex[:8]}",
                    "content": content_str,
                })

        return openai_msgs

    def _format_openai_tools(self, tool_definitions: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            }
            for td in tool_definitions
        ]

    def generate_turn(
        self,
        messages: list[AgentMessage],
        tool_definitions: list[ToolDefinition],
        timeout_seconds: Optional[float] = None,
    ) -> ModelTurnResponse:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured for live OpenAIProvider.")

        url = "https://api.openai.com/v1/chat/completions"
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._format_openai_messages(messages),
            "temperature": 0.1,
        }

        if tool_definitions:
            body["tools"] = self._format_openai_tools(tool_definitions)

        timeout = timeout_seconds or self.timeout_seconds
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    choices = resp_data.get("choices", [])
                    if not choices:
                        return ModelTurnResponse(content="", tool_calls=[], raw_response=resp_data)

                    msg = choices[0].get("message", {})
                    if msg.get("refusal"):
                        return ModelTurnResponse(
                            content=f"[Provider Notice] Generation refused by provider: {msg.get('refusal')}",
                            tool_calls=[],
                            raw_response=resp_data,
                        )

                    tool_calls: list[ToolCall] = []

                    raw_tc = msg.get("tool_calls", [])
                    for tc in raw_tc:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "{}")
                        try:
                            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except Exception:
                            parsed_args = {"raw_unparsed": raw_args}
                        tool_calls.append(
                            ToolCall(
                                id=tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                name=fn.get("name", ""),
                                arguments=parsed_args,
                            )
                        )

                    usage = resp_data.get("usage", {})
                    token_usage = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }

                    return ModelTurnResponse(
                        content=msg.get("content"),
                        tool_calls=tool_calls,
                        usage=token_usage,
                        raw_response=resp_data,
                    )
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                err_detail = ""
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        err_detail = f": {exc.read().decode('utf-8')}"
                    except Exception:
                        pass
                last_error = f"{exc}{err_detail}"
                logger.warning("OpenAI API call attempt %d failed: %s", attempt + 1, last_error)
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"OpenAI API request failed after {self.max_retries + 1} attempts: {last_error}")


class MockProvider(BaseLLMProvider):
    """Configurable mock provider supporting multi-turn tool selection and deterministic responses."""

    def __init__(
        self,
        scripted_turns: Optional[list[ModelTurnResponse]] = None,
        dynamic_handler: Optional[Callable[[list[AgentMessage], list[ToolDefinition]], ModelTurnResponse]] = None,
        model_name: str = "mock-llm-v2",
    ):
        super().__init__(model_name=model_name, timeout_seconds=5.0, max_retries=0)
        self.scripted_turns = list(scripted_turns or [])
        self.dynamic_handler = dynamic_handler
        self.turn_calls_count = 0

    def get_engine_label(self) -> str:
        return "mock_llm"

    def is_live_provider(self) -> bool:
        return False

    def add_scripted_turn(self, response: ModelTurnResponse) -> None:
        self.scripted_turns.append(response)

    def generate_turn(
        self,
        messages: list[AgentMessage],
        tool_definitions: list[ToolDefinition],
        timeout_seconds: Optional[float] = None,
    ) -> ModelTurnResponse:
        self.turn_calls_count += 1

        # 1. If dynamic custom handler is registered, use it
        if self.dynamic_handler:
            return self.dynamic_handler(messages, tool_definitions)

        # 2. If scripted turns remain, consume next scripted turn
        if self.scripted_turns:
            return self.scripted_turns.pop(0)

        # 3. Default autonomous mock behavior:
        # Inspect conversation history to simulate an intelligent multi-turn agent
        tool_results = [m for m in messages if m.role == "tool"]
        tools_executed = {m.name for m in tool_results}

        # Step 1: If active mission not read, read active mission
        if "read_active_mission" not in tools_executed:
            return ModelTurnResponse(
                content="I will inspect the student's active Career Mission roadmap to understand current commitments.",
                tool_calls=[
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:6]}",
                        name="read_active_mission",
                        arguments={},
                    )
                ],
                usage={"total_tokens": 50},
            )

        # Step 2: If active mission was read, simulate a reduced availability plan variant
        if "simulate_plan_variant" not in tools_executed:
            return ModelTurnResponse(
                content="I have inspected the active mission. I will now simulate a reduced weekly pacing variant via the C++ graph engine.",
                tool_calls=[
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:6]}",
                        name="simulate_plan_variant",
                        arguments={"variant_type": "pacing_reduction", "weekly_hours": 10},
                    )
                ],
                usage={"total_tokens": 75},
            )

        # Step 3: Produce final structured decision grounded in the simulation results
        final_decision_payload = {
            "decision_category": "proposed_mission_adjustment",
            "explanation": (
                "[Mock LLM Analysis] Successfully evaluated active mission and simulated counterfactual pacing reduction. "
                "The C++20 graph engine confirms the reduced 10 hrs/week roadmap is achievable while preserving all completed work."
            ),
            "recommended_action": "Review the simulated pacing adjustment proposal in your Roadmap view.",
            "confidence_score": 0.95,
            "tradeoffs": [
                "Preserves 100% of verified completed milestone tasks without regression.",
                "Adjusts weekly commitment to 10 hrs/week, avoiding student burnout.",
                "Curriculum graph validated via native Kahn's topological sort.",
            ],
            "suggested_proposal_title": "Pacing Adjustment: Manageable Pacing for Upcoming Constraints",
            "suggested_proposal_rationale": "Counterfactual simulation demonstrates that adjusted pacing maintains steady runway.",
        }

        return ModelTurnResponse(
            content=json.dumps(final_decision_payload),
            tool_calls=[],
            usage={"total_tokens": 120},
        )
