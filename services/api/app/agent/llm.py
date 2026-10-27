"""LLM provider adapter with safe deterministic fallback for InternPath AI.

Supports:
- Gemini (via Google AI REST API with GEMINI_API_KEY)
- OpenAI (via OpenAI REST API with OPENAI_API_KEY)
- Mock LLM (for automated testing without external network calls)
- Pure deterministic fallback labeled 'deterministic_rules' when no key is set or call fails.

Ensures:
- Configurable provider and model via environment variables or constructor
- Strict Pydantic output validation (AgentDecisionResult)
- Anonymization and minimization of sensitive student profile fields
- Safe timeouts (default 8.0s) and bounded retries (max 2 retries)
- Truthful execution labeling:
  * 'gemini:<model>' ONLY if live Gemini request succeeded
  * 'openai:<model>' ONLY if live OpenAI request succeeded
  * 'mock_llm' if mock provider
  * 'deterministic_rules' on fallback or when unconfigured
- Never store private chain-of-thought; stores concise factual explanations.
"""
import os
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Any
from app.schemas import AgentDecisionResult

logger = logging.getLogger("internpath.agent.llm")


def sanitize_student_context(data: dict[str, Any]) -> dict[str, Any]:
    """Anonymize and minimize student context before LLM consumption."""
    sanitized = {}
    for k, v in data.items():
        if k in ("email", "student_email", "password", "token", "secret", "api_key"):
            continue
        if k == "name":
            sanitized["student_name"] = "Student [Anonymized]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_student_context(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_student_context(x) if isinstance(x, dict) else x for x in v
            ]
        else:
            sanitized[k] = v
    return sanitized


class LLMAdapter:
    """Bounded LLM Adapter for agent reasoning and trade-off synthesis."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 8.0,
        max_retries: int = 2,
    ):
        self.provider = (
            provider
            or os.environ.get("INTERNPATH_LLM_PROVIDER")
            or "deterministic"
        ).lower().strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")

        if self.provider == "gemini":
            self.model = model or os.environ.get("INTERNPATH_LLM_MODEL") or "gemini-1.5-flash"
        elif self.provider == "openai":
            self.model = model or os.environ.get("INTERNPATH_LLM_MODEL") or "gpt-4o-mini"
        elif self.provider == "mock":
            self.model = model or "mock-llm-v1"
        else:
            self.provider = "deterministic"
            self.model = "rule_engine"

    def is_llm_available(self) -> bool:
        """Check if an active LLM provider with API key or mock is available."""
        if self.provider == "mock":
            return True
        if self.provider == "gemini" and bool(self.gemini_key):
            return True
        if self.provider == "openai" and bool(self.openai_key):
            return True
        return False

    def get_engine_label(self) -> str:
        """Return truthful label for audit logging."""
        if self.is_llm_available():
            if self.provider == "mock":
                return "mock_llm"
            return f"{self.provider}:{self.model}"
        return "deterministic_rules"

    def get_configured_label(self) -> str:
        """Return label indicating configured provider and model."""
        if self.provider in ("gemini", "openai"):
            return f"{self.provider}:{self.model}"
        if self.provider == "mock":
            return "mock_llm"
        return "deterministic_rules"

    def get_provider(self):
        """Return multi-turn BaseLLMProvider instance for R2.2 agent loop."""
        from app.agent.providers import GeminiProvider, OpenAIProvider, MockProvider

        if self.provider == "gemini":
            return GeminiProvider(
                api_key=self.gemini_key,
                model_name=self.model,
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        elif self.provider == "openai":
            return OpenAIProvider(
                api_key=self.openai_key,
                model_name=self.model,
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
            )
        elif self.provider == "mock":
            return MockProvider(model_name=self.model)
        else:
            return MockProvider(model_name="deterministic_rules")

    def synthesize_decision(
        self,
        event_summary: dict[str, Any],
        deterministic_result: dict[str, Any],
        student_context: dict[str, Any],
        mission_summary: dict[str, Any],
    ) -> tuple[AgentDecisionResult, str, dict[str, Any]]:
        """Synthesize agent decision using LLM if available, else deterministic rules.

        Returns:
            (AgentDecisionResult, engine_used, telemetry_metadata)
        """
        # Baseline deterministic result
        fallback_decision = AgentDecisionResult(
            decision_category=deterministic_result["decision_category"],
            explanation=deterministic_result["explanation"],
            recommended_action=deterministic_result.get("recommended_action", "Proceed according to plan."),
            confidence_score=1.0,
            tradeoffs=[
                f"Pacing capacity utilization: {deterministic_result.get('metrics', {}).get('capacity_ratio', 1.0) * 100:.0f}%",
                "Deterministic rule calculation based on verified curriculum roadmap constraints.",
            ],
            suggested_proposal_title=(
                f"Pacing Adjustment: Application Deadline Moved to {event_summary.get('new_value', 'New Date')}"
                if deterministic_result["decision_category"] == "proposed_mission_adjustment"
                else None
            ),
            suggested_proposal_rationale=(
                deterministic_result["explanation"]
                if deterministic_result["decision_category"] == "proposed_mission_adjustment"
                else None
            ),
        )

        if not self.is_llm_available():
            return fallback_decision, "deterministic_rules", {
                "tokens_used": 0,
                "fallback": False,
                "reason": "no_key_or_deterministic_mode",
            }

        # Handle Mock LLM provider (useful for deterministic test suites)
        if self.provider == "mock":
            mock_res = AgentDecisionResult(
                decision_category=deterministic_result["decision_category"],
                explanation=f"[Mock LLM Analysis] {deterministic_result['explanation']}",
                recommended_action=deterministic_result.get("recommended_action", "Review proposal."),
                confidence_score=0.95,
                tradeoffs=[
                    "Preserves verified completed skills without modification.",
                    "Optimizes milestone runway within available weekly study commitment.",
                ],
                suggested_proposal_title=fallback_decision.suggested_proposal_title,
                suggested_proposal_rationale=fallback_decision.suggested_proposal_rationale,
            )
            return mock_res, "mock_llm", {"tokens_used": 150, "mock": True, "fallback": False}

        # Prepare sanitized prompt for real provider
        clean_context = sanitize_student_context(student_context)
        prompt_payload = {
            "task": "Evaluate internship event impact on student Career Mission",
            "event": event_summary,
            "deterministic_metrics": deterministic_result,
            "student_profile": clean_context,
            "mission_summary": mission_summary,
            "instructions": (
                "You are the InternPath AI Career Agent. You MUST respect deterministic feasibility findings. "
                "Never invent guaranteed internship readiness or propose impossible study pacing. "
                "Return a raw JSON object matching the schema:\n"
                "{\n"
                '  "decision_category": "no_action" | "informational_notification" | "proposed_mission_adjustment" | "human_review_required",\n'
                '  "explanation": "concise factual explanation",\n'
                '  "recommended_action": "actionable step",\n'
                '  "confidence_score": float between 0.0 and 1.0,\n'
                '  "tradeoffs": ["list of trade-offs considered"],\n'
                '  "suggested_proposal_title": "string or null",\n'
                '  "suggested_proposal_rationale": "string or null"\n'
                "}"
            ),
        }

        # Attempt call with retries
        last_error = None
        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                if self.provider == "gemini":
                    parsed, usage = self._call_gemini_api(prompt_payload)
                elif self.provider == "openai":
                    parsed, usage = self._call_openai_api(prompt_payload)
                else:
                    return fallback_decision, "deterministic_rules", {"fallback": True}

                # Validate against Pydantic schema
                result = AgentDecisionResult(**parsed)
                latency_ms = int((time.time() - t0) * 1000)
                verified_engine = f"{self.provider}:{self.model}"
                telemetry = {
                    "tokens_used": usage.get("totalTokens") or usage.get("total_tokens") or 0,
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                    "fallback": False,
                }
                return result, verified_engine, telemetry

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM call attempt %d failed for %s (%s).",
                    attempt + 1,
                    self.provider,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        logger.warning(
            "All LLM attempts failed. Falling back safely to deterministic rules: %s",
            last_error,
        )
        return fallback_decision, "deterministic_rules", {
            "tokens_used": 0,
            "fallback": True,
            "error": str(last_error),
        }

    def _call_gemini_api(self, prompt_dict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.gemini_key}"
        )
        system_instruction = (
            "You are a strict JSON career advisor assistant. You analyze student readiness and roadmap pacing. "
            "Never override deterministic constraints. Always reply with raw JSON only."
        )
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction + "\n\n" + json.dumps(prompt_dict)}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text_out = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed_json = json.loads(text_out)
            usage = data.get("usageMetadata", {})
            return parsed_json, usage

    def _call_openai_api(self, prompt_dict: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        url = "https://api.openai.com/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the InternPath AI Career Agent. Output strictly valid JSON without code fences."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt_dict)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed_json = json.loads(content)
            usage = data.get("usage", {})
            return parsed_json, usage
