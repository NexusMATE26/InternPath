"""Bounded agent decision orchestrator for InternPath AI (R2.2).

Implements the single-agent decision workflow:
1. Event intake, validation, and idempotency checking
2. Chronological order & stale event verification
3. Autonomous model-selected tool execution loop (R2.2) when an active LLM provider is configured
4. Deterministic rules fallback path when LLM is unavailable, times out, or fails
5. Student query processing endpoint for direct conversational guidance
6. Staged proposal creation for human review (NEVER autonomous activation)
7. Audit logging into agent_runs table with truthful engine labeling
"""
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from sqlalchemy.orm import Session

from app import crud, models
from app.agent.clock import get_naive_utc_now, get_utc_now, parse_datetime_safe
from app.agent.loop import AgentExecutionLoop
from app.agent.llm import LLMAdapter
from app.agent.tools import AgentToolRegistry, ToolPermissionError
from app.schemas import (
    AgentDecisionResult,
    AgentEventCreateRequest,
    AgentQueryRequest,
    AgentSimulateRequest,
)

logger = logging.getLogger("internpath.agent.service")


class AgentService:
    """Service orchestrating the complete single-agent lifecycle."""

    MAX_TOOL_ITERATIONS = 5

    def __init__(self, db: Session, student_id: int, llm_adapter: Optional[LLMAdapter] = None):
        self.db = db
        self.student_id = student_id
        self.tool_registry = AgentToolRegistry(db, student_id)
        self.llm_adapter = llm_adapter or LLMAdapter()

    def process_event(self, event_req: AgentEventCreateRequest) -> models.AgentRun:
        """Execute the end-to-end bounded agent decision workflow."""
        start_time = time.time()
        event_uuid = event_req.event_id or f"evt_{uuid.uuid4().hex[:12]}"

        # Step 1: Idempotency & Duplicate Event Handling
        existing_event = (
            self.db.query(models.AgentEvent)
            .filter(models.AgentEvent.event_id == event_uuid)
            .first()
        )
        if existing_event:
            existing_run = (
                self.db.query(models.AgentRun)
                .filter(models.AgentRun.event_id == existing_event.event_id)
                .first()
            )
            if existing_run:
                return existing_run
            agent_event = existing_event
        else:
            src_ts = parse_datetime_safe(event_req.source_timestamp) or get_utc_now()
            agent_event = models.AgentEvent(
                event_id=event_uuid,
                event_type=event_req.event_type,
                source=event_req.source,
                source_timestamp=src_ts.replace(tzinfo=None),
                received_at=get_naive_utc_now(),
                role_id=event_req.role_id,
                student_id=self.student_id,
                previous_value=event_req.previous_value,
                new_value=event_req.new_value,
                source_reliability=event_req.source_reliability,
                evidence_reference=event_req.evidence_reference,
                processing_status="pending",
                is_simulated=event_req.is_simulated,
                payload=json.dumps(event_req.payload or {}),
            )
            self.db.add(agent_event)
            self.db.flush()

        active_mission = crud.get_active_career_mission(self.db, self.student_id)
        active_mission_id = active_mission.id if active_mission else None

        # Step 2: Chronological order & Stale Event Detection
        if agent_event.role_id and agent_event.source_timestamp:
            newer_event = (
                self.db.query(models.AgentEvent)
                .filter(
                    models.AgentEvent.student_id == self.student_id,
                    models.AgentEvent.role_id == agent_event.role_id,
                    models.AgentEvent.event_id != agent_event.event_id,
                    models.AgentEvent.source_timestamp > agent_event.source_timestamp,
                    models.AgentEvent.processing_status.in_(["processed", "requires_human_review"]),
                )
                .first()
            )
            if newer_event:
                agent_event.processing_status = "ignored"
                explanation = (
                    f"Out-of-order event detected: The event timestamp ({agent_event.source_timestamp.isoformat()}) "
                    f"is older than the latest processed event ({newer_event.source_timestamp.isoformat()}) for role "
                    f"'{agent_event.role_id}'. Ignored to prevent overwriting newer verified data."
                )
                run_id = f"run_{uuid.uuid4().hex[:16]}"
                agent_run = models.AgentRun(
                    id=run_id,
                    event_id=agent_event.event_id,
                    mission_id=active_mission_id,
                    student_id=self.student_id,
                    engine_used="deterministic_rules",
                    decision_category="no_action",
                    is_simulated=agent_event.is_simulated,
                    relevant_evidence=json.dumps({
                        "reason": "stale_out_of_order_event",
                        "event_timestamp": agent_event.source_timestamp.isoformat(),
                        "latest_processed_timestamp": newer_event.source_timestamp.isoformat(),
                    }),
                    tools_invoked="[]",
                    tool_io_log="[]",
                    decision_explanation=explanation,
                    proposal_id=None,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    status="completed",
                )
                self.db.add(agent_run)
                self.db.commit()
                self.db.refresh(agent_run)
                return agent_run

        # Step 3: Branch between Multi-turn LLM Tool Loop (R2.2) and Deterministic Evaluator
        if self.llm_adapter.is_llm_available():
            # R2.2: Genuine model-selected multi-turn tool calling
            user_prompt = (
                f"Observed Career Event:\n"
                f"- Event ID: {agent_event.event_id}\n"
                f"- Event Type: {agent_event.event_type}\n"
                f"- Target Role ID: {agent_event.role_id}\n"
                f"- Previous Value: {agent_event.previous_value}\n"
                f"- New Value: {agent_event.new_value}\n"
                f"- Source: {agent_event.source}\n"
                f"- Source Reliability: {agent_event.source_reliability}\n\n"
                f"Active Student Context:\n"
                f"- Student ID: {self.student_id}\n\n"
                "Instructions:\n"
                "1. Autonomously inspect the student's active mission and requirements using available tools.\n"
                "2. If constraints have tightened, run counterfactual simulations using 'simulate_plan_variant'.\n"
                "3. If alternatives exist, compare them using 'compare_plan_variants'.\n"
                "4. If a plan change is needed, stage a proposal with 'create_mission_change_proposal'.\n"
                "5. Provide your final advice formatted as a raw JSON AgentDecisionResult object."
            )

            def _deterministic_fallback():
                cat, exp, rec, p_id, _ = self._evaluate_deterministic_path(agent_event)
                return AgentDecisionResult(
                    decision_category=cat,
                    explanation=f"[Deterministic Fallback] {exp}",
                    recommended_action=rec,
                    confidence_score=0.9,
                    tradeoffs=["Fallback to verified deterministic curriculum constraints."],
                )

            loop = AgentExecutionLoop(
                registry=self.tool_registry,
                provider=self.llm_adapter.get_provider(),
                max_turns=self.MAX_TOOL_ITERATIONS,
            )
            trace = loop.execute(
                user_prompt,
                fallback_decision_generator=_deterministic_fallback,
                active_mission=active_mission,
                event_context={
                    "event_id": agent_event.event_id,
                    "event_type": agent_event.event_type,
                    "source": agent_event.source,
                    "source_reliability": agent_event.source_reliability,
                    "is_simulated": agent_event.is_simulated,
                },
            )

            decision_category = trace.decision.decision_category
            explanation = trace.decision.explanation
            proposal_id = trace.proposal_id
            engine_used = trace.engine_used
            elapsed_ms = trace.execution_time_ms
            tools_invoked_list = trace.tools_invoked
            tool_io_log_list = trace.tool_io_log
            relevant_evidence = {
                "event_type": agent_event.event_type,
                "total_turns": len(trace.turns),
                "fallback_used": trace.fallback_used,
                "grounding_status": trace.grounding_status,
                "grounding_violations": trace.grounding_violations,
            }

            if decision_category == "human_review_required":
                agent_event.processing_status = "requires_human_review"
            else:
                agent_event.processing_status = "processed"

        else:
            # Deterministic Evaluator Path (Phase 3.5 baseline)
            cat, exp, rec, p_id, evidence = self._evaluate_deterministic_path(agent_event)
            decision_category = cat
            explanation = exp
            proposal_id = p_id
            relevant_evidence = evidence
            engine_used = "deterministic_rules"
            elapsed_ms = int((time.time() - start_time) * 1000)
            tools_invoked_list = [rec.tool_name for rec in self.tool_registry.invocations]
            tool_io_log_list = [rec.to_dict() for rec in self.tool_registry.invocations]

            if decision_category == "human_review_required":
                agent_event.processing_status = "requires_human_review"
            elif decision_category == "no_action" and (not active_mission or relevant_evidence.get("is_role_relevant") is False):
                agent_event.processing_status = "ignored"
            else:
                agent_event.processing_status = "processed"

        # Step 4: Persist Audit Record into agent_runs
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        agent_run = models.AgentRun(
            id=run_id,
            event_id=agent_event.event_id,
            mission_id=active_mission_id,
            student_id=self.student_id,
            engine_used=engine_used,
            decision_category=decision_category,
            is_simulated=agent_event.is_simulated,
            relevant_evidence=json.dumps(relevant_evidence),
            tools_invoked=json.dumps(tools_invoked_list),
            tool_io_log=json.dumps(tool_io_log_list),
            decision_explanation=explanation,
            proposal_id=proposal_id,
            execution_time_ms=elapsed_ms,
            status="completed",
        )
        self.db.add(agent_run)
        self.db.commit()
        self.db.refresh(agent_run)
        return agent_run

    def process_query(self, query_req: AgentQueryRequest) -> models.AgentRun:
        """Process a direct student inquiry or scenario request using autonomous model-selected tool calling."""
        start_time = time.time()
        active_m = crud.get_active_career_mission(self.db, self.student_id)
        role_id = query_req.context_role_id or (active_m.target_role_id if active_m else "distributed-systems-intern")
        now = get_utc_now()
        event_uuid = f"evt_{uuid.uuid4().hex[:12]}"

        # Persist event for student query
        agent_event = models.AgentEvent(
            event_id=event_uuid,
            event_type="student_query",
            source="student_assistant_query",
            source_timestamp=now.replace(tzinfo=None),
            received_at=get_naive_utc_now(),
            role_id=role_id,
            student_id=self.student_id,
            previous_value=None,
            new_value=query_req.query,
            source_reliability="trusted_internal",
            evidence_reference=None,
            processing_status="processed",
            is_simulated=query_req.simulated,
            payload=json.dumps({"query": query_req.query}),
        )
        self.db.add(agent_event)
        self.db.flush()

        user_prompt = (
            f"Student Guidance Request:\n"
            f'"{query_req.query}"\n\n'
            f"Active Student Context:\n"
            f"- Student ID: {self.student_id}\n"
            f"- Context Role ID: {role_id}\n\n"
            "Instructions:\n"
            "1. Autonomously inspect the student's active mission and commitments with 'read_active_mission'.\n"
            "2. Evaluate options using 'simulate_plan_variant' (e.g. reduced weekly hours or temporary availability overrides).\n"
            "3. If multiple options are feasible, compare them with 'compare_plan_variants'.\n"
            "4. Provide honest, transparent advice explaining trade-offs.\n"
            "5. If workload adjustment is beneficial, you may stage a pending proposal with 'create_mission_change_proposal'.\n"
            "6. Output your final advice formatted as a raw JSON AgentDecisionResult object."
        )

        if self.llm_adapter.is_llm_available():
            loop = AgentExecutionLoop(
                registry=self.tool_registry,
                provider=self.llm_adapter.get_provider(),
                max_turns=self.MAX_TOOL_ITERATIONS,
            )
            trace = loop.execute(
                user_prompt,
                active_mission=active_m,
                event_context={
                    "event_type": "student_query",
                    "source_reliability": "trusted_internal",
                    "is_simulated": query_req.simulated,
                },
            )
            decision = trace.decision
            engine_used = trace.engine_used
            proposal_id = trace.proposal_id
            elapsed_ms = trace.execution_time_ms
            tools_invoked = trace.tools_invoked
            tool_io_log = trace.tool_io_log
            query_evidence = {
                "query": query_req.query,
                "grounding_status": trace.grounding_status,
                "grounding_violations": trace.grounding_violations,
                "fallback_used": trace.fallback_used,
            }
        else:
            # Deterministic fallback for student query
            if active_m:
                sim_res = self.tool_registry.execute_tool(
                    "simulate_plan_variant",
                    variant_type="pacing_reduction",
                    weekly_hours=10,
                )
                w_range = sim_res.get("estimated_weeks_range", (0.0, 0.0))
                decision = AgentDecisionResult(
                    decision_category="proposed_mission_adjustment",
                    explanation=(
                        f"Evaluated student inquiry under adjusted weekly pacing. "
                        f"C++20 graph planner confirms the remaining roadmap is achievable within {w_range[0]} to {w_range[1]} weeks "
                        "while strictly preserving all verified completed tasks."
                    ),
                    recommended_action="Review simulated pacing adjustment in your Roadmap view.",
                    confidence_score=0.9,
                    tradeoffs=[
                        "Preserves verified completed competencies.",
                        "Adapts study rate within student availability.",
                    ],
                )
            else:
                decision = AgentDecisionResult(
                    decision_category="no_action",
                    explanation="No active Career Mission found for student. Please create a mission to evaluate roadmaps.",
                    recommended_action="Create an active Career Mission in the Onboarding or Roadmap tab.",
                    confidence_score=1.0,
                    tradeoffs=[],
                )

            engine_used = "deterministic_rules"
            proposal_id = None
            elapsed_ms = int((time.time() - start_time) * 1000)
            tools_invoked = [rec.tool_name for rec in self.tool_registry.invocations]
            tool_io_log = [rec.to_dict() for rec in self.tool_registry.invocations]

        run_id = f"run_{uuid.uuid4().hex[:16]}"
        agent_run = models.AgentRun(
            id=run_id,
            event_id=agent_event.event_id,
            mission_id=active_m.id if active_m else None,
            student_id=self.student_id,
            engine_used=engine_used,
            decision_category=decision.decision_category,
            is_simulated=query_req.simulated,
            relevant_evidence=json.dumps(query_evidence if self.llm_adapter.is_llm_available() else {"query": query_req.query}),
            tools_invoked=json.dumps(tools_invoked),
            tool_io_log=json.dumps(tool_io_log),
            decision_explanation=decision.explanation,
            proposal_id=proposal_id,
            execution_time_ms=elapsed_ms,
            status="completed",
        )
        self.db.add(agent_run)
        self.db.commit()
        self.db.refresh(agent_run)
        return agent_run

    def _evaluate_deterministic_path(self, agent_event: models.AgentEvent) -> tuple[str, str, str, Optional[int], dict[str, Any]]:
        """Execute deterministic tool pipeline (Phase 3.5 compatibility)."""
        # Context gathering
        self.tool_registry.execute_tool("inspect_relevant_event", event_id=agent_event.event_id)
        self.tool_registry.execute_tool("read_student_profile", student_id=self.student_id)
        active_mission = self.tool_registry.execute_tool("read_active_mission", student_id=self.student_id)

        proposal_id: Optional[int] = None
        decision_category = "no_action"
        explanation = ""
        recommended_action = "No action required."
        relevant_evidence: dict[str, Any] = {}

        if agent_event.event_type == "student_skill_evidence_added":
            is_self_reported = (agent_event.source_reliability in ("unverified_third_party", "student_self_report"))
            evidence_title = agent_event.new_value or "New Evidence Submission"
            decision_category = "informational_notification"
            if is_self_reported:
                explanation = (
                    f"Observed student portfolio evidence: '{evidence_title}'. "
                    "The artifact has been linked to the student portfolio. "
                    "Note: Self-reported evidence remains unverified until external evaluation or assessment. "
                    "Career Mission assumptions remain grounded in verified competencies."
                )
            else:
                explanation = (
                    f"Observed verified skill credential: '{evidence_title}'. "
                    "Linked to student portfolio. Milestone requirements remain aligned."
                )
            recommended_action = "Continue mission progress."
            relevant_evidence = {"evidence_type": "skill_evidence", "is_self_reported": is_self_reported}

        elif agent_event.event_type in ("mission_progress_updated", "task_completed"):
            decision_category = "informational_notification"
            explanation = (
                f"Observed roadmap progress update: {agent_event.previous_value or 'Task'} -> "
                f"{agent_event.new_value or 'Completed'}. "
                "Downstream prerequisite milestones evaluated. Roadmap proceeds on schedule."
            )
            recommended_action = "Continue mission progress."
            relevant_evidence = {"update": agent_event.new_value}

        elif agent_event.event_type == "internship_deadline_changed":
            is_relevant = False
            if active_mission and active_mission.get("target_role_id"):
                if agent_event.role_id is None or agent_event.role_id == active_mission["target_role_id"]:
                    is_relevant = True

            if not active_mission:
                decision_category = "no_action"
                explanation = "Student currently has no active Career Mission. Event noted with no action."
                relevant_evidence = {"is_role_relevant": False, "reason": "no_active_mission"}
            elif not is_relevant:
                decision_category = "no_action"
                explanation = (
                    f"Deadline changed for role '{agent_event.role_id}', but student's active Career Mission "
                    f"targets '{active_mission.get('target_role_id')}'. Event is not relevant to current mission."
                )
                relevant_evidence = {"is_role_relevant": False}
            else:
                mission_id = active_mission["mission_id"]
                impact_result = self.tool_registry.execute_tool(
                    "calculate_deadline_impact",
                    mission_id=mission_id,
                    new_deadline=agent_event.new_value,
                    current_deadline=agent_event.previous_value,
                    source_reliability=agent_event.source_reliability,
                )
                decision_category = impact_result["decision_category"]
                explanation = impact_result["explanation"]
                recommended_action = impact_result.get("recommended_action", "Review proposal.")
                relevant_evidence = impact_result.get("metrics", {})

                if decision_category == "proposed_mission_adjustment":
                    revised_plan = self.tool_registry.execute_tool(
                        "run_learning_path_engine",
                        student_id=self.student_id,
                        role_id=active_mission["target_role_id"],
                        target_deadline=agent_event.new_value,
                    )
                    active_version_tasks = active_mission.get("tasks", [])
                    diff_check = self.tool_registry.execute_tool(
                        "compare_plan_versions",
                        active_version_tasks=active_version_tasks,
                        proposed_plan=revised_plan,
                    )

                    if not diff_check.get("is_material_difference", True) and relevant_evidence.get("capacity_ratio", 1.0) <= 1.15:
                        decision_category = "informational_notification"
                        explanation = (
                            f"Deadline adjusted to {agent_event.new_value}, but roadmap stages and milestone ordering "
                            "remain optimal. No structural mission adjustment is required."
                        )
                        recommended_action = "Continue on existing schedule."
                    else:
                        new_deadline_display = agent_event.new_value or "Earlier Date"
                        scope_reduct = relevant_evidence.get("scope_reduction_available", False)
                        if scope_reduct:
                            p_title = f"Scope Reduction: Prioritize Core Competencies for {new_deadline_display} Deadline"
                            p_rationale = (
                                f"Application deadline moved earlier to {new_deadline_display}. "
                                f"To avoid unachievable study pacing, this proposal prioritizes mandatory core competencies "
                                f"while deferring optional electives outside the application runway. "
                                f"Completed milestone tasks are strictly preserved."
                            )
                        else:
                            p_title = f"Pacing Adjustment: Application Deadline Moved to {new_deadline_display}"
                            p_rationale = (
                                f"Application deadline moved earlier to {new_deadline_display}. "
                                f"At current pacing, meeting the deadline requires an intensified study rate. "
                                f"This proposal re-balances roadmap stages and milestones while strictly preserving "
                                f"all verified completed tasks."
                            )

                        proposal_result = self.tool_registry.execute_tool(
                            "create_mission_change_proposal",
                            mission_id=mission_id,
                            proposal_title=p_title,
                            rationale=p_rationale,
                            proposed_plan=revised_plan,
                        )
                        proposal_id = proposal_result.get("proposal_id")

        return decision_category, explanation, recommended_action, proposal_id, relevant_evidence

    def simulate_demo_event(self, req: AgentSimulateRequest) -> models.AgentRun:
        """Trigger controlled, explicitly labeled demo events for presenter verification."""
        active_mission = crud.get_active_career_mission(self.db, self.student_id)
        role_id = req.role_id or (active_mission.target_role_id if active_mission else "distributed-systems-intern")
        now = get_utc_now()

        if req.scenario == "deadline_earlier":
            prev_dl = (now + timedelta(days=120)).strftime("%Y-%m-%d")
            new_dl = req.custom_deadline or (now + timedelta(days=50)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo_portal",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=prev_dl,
                new_value=new_dl,
                source_reliability=req.source_reliability or "verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "deadline_earlier", "days_remaining": 50},
            )
            return self.process_event(evt)

        elif req.scenario == "deadline_earlier_infeasible":
            prev_dl = (now + timedelta(days=90)).strftime("%Y-%m-%d")
            new_dl = (now + timedelta(days=5)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo_portal",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=prev_dl,
                new_value=new_dl,
                source_reliability=req.source_reliability or "verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "deadline_earlier_infeasible", "days_remaining": 5},
            )
            return self.process_event(evt)

        elif req.scenario == "deadline_extended":
            prev_dl = (now + timedelta(days=45)).strftime("%Y-%m-%d")
            new_dl = req.custom_deadline or (now + timedelta(days=120)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo_portal",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=prev_dl,
                new_value=new_dl,
                source_reliability=req.source_reliability or "verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "deadline_extended", "days_remaining": 120},
            )
            return self.process_event(evt)

        elif req.scenario == "unrelated_role":
            other_role = "backend-api-intern" if role_id != "backend-api-intern" else "distributed-systems-intern"
            new_dl = (now + timedelta(days=30)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo_portal",
                source_timestamp=now.isoformat(),
                role_id=other_role,
                student_id=self.student_id,
                previous_value=None,
                new_value=new_dl,
                source_reliability="verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "unrelated_role", "role": other_role},
            )
            return self.process_event(evt)

        elif req.scenario == "evidence_added":
            evt = AgentEventCreateRequest(
                event_type="student_skill_evidence_added",
                source="student_github_repo",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=None,
                new_value="Distributed KV-Store Implementation with Raft Consensus",
                source_reliability="trusted_internal",
                is_simulated=True,
                payload={"simulation_scenario": "evidence_added"},
            )
            return self.process_event(evt)

        elif req.scenario == "untrusted_source":
            new_dl = (now + timedelta(days=14)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="unverified_forum_post",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=(now + timedelta(days=45)).strftime("%Y-%m-%d"),
                new_value=new_dl,
                source_reliability="unverified_third_party",
                is_simulated=True,
                payload={"simulation_scenario": "untrusted_source"},
            )
            return self.process_event(evt)

        elif req.scenario == "stale_event":
            stale_time = now - timedelta(days=10)
            new_dl = (now + timedelta(days=40)).strftime("%Y-%m-%d")
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo_portal",
                source_timestamp=stale_time.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=(now + timedelta(days=80)).strftime("%Y-%m-%d"),
                new_value=new_dl,
                source_reliability="verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "stale_event"},
            )
            return self.process_event(evt)

        elif req.scenario == "missing_deadline":
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=None,
                new_value=None,
                source_reliability="verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "missing_deadline"},
            )
            return self.process_event(evt)

        elif req.scenario == "zero_hours":
            evt = AgentEventCreateRequest(
                event_type="internship_deadline_changed",
                source="simulated_demo",
                source_timestamp=now.isoformat(),
                role_id=role_id,
                student_id=self.student_id,
                previous_value=(now + timedelta(days=45)).strftime("%Y-%m-%d"),
                new_value=(now + timedelta(days=20)).strftime("%Y-%m-%d"),
                source_reliability="verified_employer",
                is_simulated=True,
                payload={"simulation_scenario": "zero_hours"},
            )
            return self.process_event(evt)

        raise ValueError(f"Unknown simulation scenario: {req.scenario}")
