"""Bounded multi-turn agent execution loop for InternPath AI (R2.2).

Orchestrates the model-selected tool calling lifecycle:
1. System prompt injection (grounding invariants, tool rules, student approval mandate)
2. Context presentation to the model
3. Multi-turn model reasoning & autonomous tool selection
4. Authorized Python/C++ tool dispatch via AgentToolRegistry
5. Tool result feedback into model conversation context
6. Bounded termination (max turns, max tool calls, strict timeouts)
7. Final decision synthesis validation and fallback recovery
8. Explainable audit trace generation for AgentRun persistence
"""
import json
import logging
import os
import re
import time
from typing import Any, Optional

from app.agent.grounding import GroundingValidator
from app.agent.providers import BaseLLMProvider
from app.agent.tools import AgentToolRegistry, ToolPermissionError
from app.agent.types import (
    AgentExecutionTrace,
    AgentMessage,
    AgentTurnRecord,
    ModelTurnResponse,
    ToolCall,
    ToolResult,
)
from app.schemas import AgentDecisionResult, ToolDefinition

logger = logging.getLogger("internpath.agent.loop")


class AgentExecutionLoop:
    """Bounded, authenticated multi-turn agent execution loop."""

    DEFAULT_MAX_TURNS = 5
    DEFAULT_MAX_TOOL_CALLS = 8
    DEFAULT_OVERALL_TIMEOUT = 90.0
    DEFAULT_TURN_TIMEOUT = 30.0

    def __init__(
        self,
        registry: AgentToolRegistry,
        provider: BaseLLMProvider,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        overall_timeout_seconds: Optional[float] = None,
        turn_timeout_seconds: Optional[float] = None,
    ):
        self.registry = registry
        self.provider = provider
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls

        if overall_timeout_seconds is None:
            env_val = os.environ.get("INTERNPATH_AGENT_TIMEOUT_SECONDS")
            try:
                self.overall_timeout_seconds = float(env_val) if env_val else self.DEFAULT_OVERALL_TIMEOUT
            except ValueError:
                self.overall_timeout_seconds = self.DEFAULT_OVERALL_TIMEOUT
        else:
            self.overall_timeout_seconds = overall_timeout_seconds

        if turn_timeout_seconds is None:
            env_val = os.environ.get("INTERNPATH_LLM_TIMEOUT_SECONDS")
            try:
                self.turn_timeout_seconds = float(env_val) if env_val else self.DEFAULT_TURN_TIMEOUT
            except ValueError:
                self.turn_timeout_seconds = self.DEFAULT_TURN_TIMEOUT
        else:
            self.turn_timeout_seconds = turn_timeout_seconds

    def _build_system_instruction(self) -> str:
        return (
            "You are the InternPath AI Career Agent, an autonomous career readiness companion for engineering undergraduates.\n\n"
            "CRITICAL ARCHITECTURAL INVARIANTS:\n"
            "1. THE AI PROPOSES. THE ALGORITHMS VALIDATE. THE STUDENT DECIDES.\n"
            "2. You have access to real deterministic tools. You must use tools like 'read_active_mission', "
            "'simulate_plan_variant', and 'compare_plan_variants' to inspect facts and test options.\n"
            "3. You CANNOT approve proposals or mutate student missions directly. Any plan change must be staged via "
            "'create_mission_change_proposal' in PENDING status, awaiting human student review.\n"
            "4. Never invent nonexistent tools, simulated results, or deadlines. Base all decisions on actual tool output.\n"
            "5. When you have gathered sufficient information to advise the student, output your final response as a RAW JSON object "
            "matching the following schema:\n"
            "{\n"
            '  "decision_category": "no_action" | "informational_notification" | "proposed_mission_adjustment" | "human_review_required",\n'
            '  "explanation": "concise factual explanation grounded in tool results",\n'
            '  "recommended_action": "actionable guidance for student",\n'
            '  "confidence_score": 0.0 to 1.0,\n'
            '  "tradeoffs": ["key trade-off 1", "key trade-off 2"],\n'
            '  "suggested_proposal_title": "string or null",\n'
            '  "suggested_proposal_rationale": "string or null"\n'
            "}\n"
        )

    def _extract_decision_json(self, text: Optional[str]) -> Optional[AgentDecisionResult]:
        """Parse raw model text into AgentDecisionResult, handling potential markdown code blocks."""
        if not text:
            return None

        clean_text = text.strip()
        # Strip markdown fences if present
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r"\s*```$", "", clean_text, flags=re.MULTILINE).strip()

        # Try to locate JSON object
        json_match = re.search(r"\{.*\}", clean_text, re.DOTALL)
        if json_match:
            candidate_str = json_match.group(0)
            try:
                data = json.loads(candidate_str)
                return AgentDecisionResult(**data)
            except Exception as exc:
                logger.debug("Failed parsing extracted JSON into AgentDecisionResult: %s", exc)

        return None

    def execute(
        self,
        initial_user_prompt: str,
        fallback_decision_generator: Optional[Any] = None,
        active_mission: Optional[Any] = None,
        event_context: Optional[dict[str, Any]] = None,
    ) -> AgentExecutionTrace:
        """Run the bounded multi-turn agent loop to conclusion or safe fallback."""
        start_time = time.time()
        tool_definitions = self.registry.get_tool_definitions()

        messages: list[AgentMessage] = [
            AgentMessage(role="system", content=self._build_system_instruction()),
            AgentMessage(role="user", content=initial_user_prompt),
        ]

        turns_audit: list[AgentTurnRecord] = []
        tools_invoked_names: list[str] = []
        total_tool_calls_count = 0
        total_tokens_count = 0
        staged_proposal_id: Optional[int] = None
        has_staged_proposal = False

        for turn_idx in range(1, self.max_turns + 1):
            turn_start = time.time()
            elapsed_total = time.time() - start_time
            remaining_overall = self.overall_timeout_seconds - elapsed_total

            if remaining_overall <= 0 or elapsed_total > self.overall_timeout_seconds:
                logger.warning("Agent loop overall timeout exceeded (%.1fs > %.1fs).", elapsed_total, self.overall_timeout_seconds)
                return self._fallback_response(
                    reason="overall_timeout_exceeded",
                    turns=turns_audit,
                    tools_invoked=tools_invoked_names,
                    total_tool_calls=total_tool_calls_count,
                    total_tokens=total_tokens_count,
                    proposal_id=staged_proposal_id,
                    fallback_gen=fallback_decision_generator,
                    start_time=start_time,
                )

            # If remaining overall budget is too tight for an LLM turn + potential tool calls,
            # trigger graceful fallback rather than timing out unproductively mid-flight.
            if remaining_overall < 2.0:
                logger.warning(
                    "Agent loop overall time budget nearly exhausted (%.1fs remaining < 2.0s).",
                    remaining_overall,
                )
                return self._fallback_response(
                    reason="overall_timeout_exceeded",
                    turns=turns_audit,
                    tools_invoked=tools_invoked_names,
                    total_tool_calls=total_tool_calls_count,
                    total_tokens=total_tokens_count,
                    proposal_id=staged_proposal_id,
                    fallback_gen=fallback_decision_generator,
                    start_time=start_time,
                )

            # Turn timeout is bounded by both configured turn timeout and remaining overall budget
            turn_timeout = min(self.turn_timeout_seconds, remaining_overall)

            # Request turn from provider
            try:
                turn_resp: ModelTurnResponse = self.provider.generate_turn(
                    messages=messages,
                    tool_definitions=tool_definitions,
                    timeout_seconds=turn_timeout,
                )
            except Exception as exc:
                logger.warning("Provider generate_turn error on turn %d: %s", turn_idx, exc)
                return self._fallback_response(
                    reason=f"provider_error: {exc}",
                    turns=turns_audit,
                    tools_invoked=tools_invoked_names,
                    total_tool_calls=total_tool_calls_count,
                    total_tokens=total_tokens_count,
                    proposal_id=staged_proposal_id,
                    fallback_gen=fallback_decision_generator,
                    start_time=start_time,
                )

            # Accumulate token usage
            total_tokens_count += turn_resp.usage.get("total_tokens", 0)

            # -------------------------------------------------------------
            # Case 1: Model requested tool calls
            # -------------------------------------------------------------
            if turn_resp.tool_calls:
                turn_calls_data: list[dict[str, Any]] = []
                turn_results_data: list[dict[str, Any]] = []

                # Append assistant message with requested tool calls to history
                messages.append(
                    AgentMessage(
                        role="assistant",
                        content=turn_resp.content,
                        tool_calls=turn_resp.tool_calls,
                    )
                )

                for tc in turn_resp.tool_calls:
                    total_tool_calls_count += 1
                    turn_calls_data.append({"id": tc.id, "name": tc.name, "arguments": tc.arguments})
                    tools_invoked_names.append(tc.name)

                    # Check tool call budget
                    if total_tool_calls_count > self.max_tool_calls:
                        err_msg = f"Tool call budget exceeded ({self.max_tool_calls} calls limit reached)."
                        turn_results_data.append({"tool": tc.name, "error": err_msg})
                        messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=json.dumps({"error": "budget_exceeded", "message": err_msg}),
                            )
                        )
                        continue

                    # Idempotency guard for write operation (create_mission_change_proposal)
                    if tc.name == "create_mission_change_proposal" and has_staged_proposal:
                        warn_msg = f"A mission proposal (#{staged_proposal_id}) has already been staged for this evaluation. Duplicate staging skipped."
                        turn_results_data.append({"tool": tc.name, "warning": warn_msg, "proposal_id": staged_proposal_id})
                        messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=json.dumps({"status": "already_staged", "proposal_id": staged_proposal_id, "message": warn_msg}),
                            )
                        )
                        continue

                    # Dispatch tool execution through bounded registry
                    try:
                        raw_result = self.registry.execute_tool(tc.name, **tc.arguments)
                        if tc.name == "create_mission_change_proposal" and isinstance(raw_result, dict):
                            staged_proposal_id = raw_result.get("proposal_id")
                            has_staged_proposal = True

                        turn_results_data.append({"tool": tc.name, "output": raw_result})
                        messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=raw_result if isinstance(raw_result, str) else json.dumps(raw_result, default=str),
                            )
                        )
                    except ToolPermissionError as perm_err:
                        err_payload = {"error": "permission_denied", "reason": str(perm_err)}
                        turn_results_data.append({"tool": tc.name, "error": str(perm_err)})
                        messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=json.dumps(err_payload),
                            )
                        )
                    except Exception as tool_err:
                        err_payload = {"error": type(tool_err).__name__, "message": str(tool_err)}
                        turn_results_data.append({"tool": tc.name, "error": str(tool_err)})
                        messages.append(
                            AgentMessage(
                                role="tool",
                                tool_call_id=tc.id,
                                name=tc.name,
                                content=json.dumps(err_payload),
                            )
                        )

                turn_duration = int((time.time() - turn_start) * 1000)
                turns_audit.append(
                    AgentTurnRecord(
                        turn_index=turn_idx,
                        model_tool_calls=turn_calls_data,
                        tool_results=turn_results_data,
                        assistant_message=turn_resp.content,
                        duration_ms=turn_duration,
                    )
                )

            # -------------------------------------------------------------
            # Case 2: Model produced final text response (no tool calls)
            # -------------------------------------------------------------
            else:
                decision = self._extract_decision_json(turn_resp.content)
                turn_duration = int((time.time() - turn_start) * 1000)
                turns_audit.append(
                    AgentTurnRecord(
                        turn_index=turn_idx,
                        model_tool_calls=[],
                        tool_results=[],
                        assistant_message=turn_resp.content,
                        duration_ms=turn_duration,
                    )
                )

                if decision:
                    # Grounding validation: verify model claims against simulation and database facts
                    grounding_res = GroundingValidator.validate_decision(
                        decision=decision,
                        tools_invoked=tools_invoked_names,
                        tool_io_log=[rec.to_dict() for rec in self.registry.invocations],
                        simulation_cache=self.registry.simulation_cache,
                        active_mission=active_mission,
                        event_context=event_context,
                    )
                    decision = grounding_res.validated_decision
                    violations_str = [f"[{v.category}] {v.message}" for v in grounding_res.violations]

                    # Grounding validation: link staged proposal if created
                    if staged_proposal_id and decision.decision_category == "proposed_mission_adjustment":
                        if not decision.suggested_proposal_title:
                            decision.suggested_proposal_title = "Plan Adjustment Proposal Staged by Agent"

                    total_elapsed = int((time.time() - start_time) * 1000)
                    return AgentExecutionTrace(
                        engine_used=self.provider.get_engine_label(),
                        decision=decision,
                        turns=turns_audit,
                        tools_invoked=tools_invoked_names,
                        tool_io_log=[rec.to_dict() for rec in self.registry.invocations],
                        total_tool_calls=total_tool_calls_count,
                        proposal_id=staged_proposal_id,
                        total_tokens=total_tokens_count,
                        execution_time_ms=total_elapsed,
                        fallback_used=False,
                        grounding_status=grounding_res.status,
                        grounding_violations=violations_str,
                    )
                else:
                    logger.warning("Model produced non-JSON text on turn %d: %s", turn_idx, turn_resp.content)
                    # Ask model once to format into JSON if turns remain, else fallback
                    if turn_idx < self.max_turns:
                        messages.append(AgentMessage(role="assistant", content=turn_resp.content))
                        messages.append(
                            AgentMessage(
                                role="user",
                                content="Please format your final advice into the required raw JSON AgentDecisionResult object.",
                            )
                        )
                    else:
                        return self._fallback_response(
                            reason="malformed_final_output_unparseable_json",
                            turns=turns_audit,
                            tools_invoked=tools_invoked_names,
                            total_tool_calls=total_tool_calls_count,
                            total_tokens=total_tokens_count,
                            proposal_id=staged_proposal_id,
                            fallback_gen=fallback_decision_generator,
                            start_time=start_time,
                        )

        # Max turns exhausted without final JSON decision
        return self._fallback_response(
            reason="max_turns_exhausted",
            turns=turns_audit,
            tools_invoked=tools_invoked_names,
            total_tool_calls=total_tool_calls_count,
            total_tokens=total_tokens_count,
            proposal_id=staged_proposal_id,
            fallback_gen=fallback_decision_generator,
            start_time=start_time,
        )

    def _fallback_response(
        self,
        reason: str,
        turns: list[AgentTurnRecord],
        tools_invoked: list[str],
        total_tool_calls: int,
        total_tokens: int,
        proposal_id: Optional[int],
        fallback_gen: Optional[Any],
        start_time: float,
    ) -> AgentExecutionTrace:
        """Produce safe deterministic fallback decision while preserving complete execution history."""
        total_elapsed = int((time.time() - start_time) * 1000)

        if fallback_gen and callable(fallback_gen):
            fallback_decision = fallback_gen()
        else:
            fallback_decision = AgentDecisionResult(
                decision_category="human_review_required",
                explanation=f"Autonomous agent reasoning encountered an execution limitation ({reason}). Fallback to deterministic rules applied.",
                recommended_action="Review current roadmap and consult contextual assistant recommendations.",
                confidence_score=0.8,
                tradeoffs=["Fallback to verified deterministic curriculum constraints."],
            )

        return AgentExecutionTrace(
            engine_used="deterministic_rules",
            decision=fallback_decision,
            turns=turns,
            tools_invoked=tools_invoked,
            tool_io_log=[rec.to_dict() for rec in self.registry.invocations],
            total_tool_calls=total_tool_calls,
            proposal_id=proposal_id,
            total_tokens=total_tokens,
            execution_time_ms=total_elapsed,
            fallback_used=True,
            fallback_reason=reason,
            grounding_status="deterministic_verified",
            grounding_violations=[],
        )
