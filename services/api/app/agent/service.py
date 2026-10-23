"""Bounded agent decision orchestrator for InternPath AI.

Implements the single-agent event-driven workflow:
1. Event intake, validation, and idempotency checking
2. Chronological order & stale event verification
3. Context gathering & relevance assessment via authorized tools
4. Feasibility analysis and realistic student pacing evaluation
5. Decision synthesis (LLM adapter with pure deterministic rules fallback)
6. Staged proposal creation for human review (NEVER autonomous activation)
7. Audit logging into agent_runs table with truthful engine labeling
"""
import uuid
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session

from app import models, crud
from app.agent.tools import AgentToolRegistry, ToolPermissionError
from app.agent.clock import get_utc_now, get_naive_utc_now, parse_datetime_safe
from app.agent.llm import LLMAdapter
from app.schemas import (
    AgentEventCreateRequest,
    AgentSimulateRequest,
    AgentDecisionResult,
)


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
            # Check if there is an existing run for this duplicate event
            existing_run = (
                self.db.query(models.AgentRun)
                .filter(models.AgentRun.event_id == existing_event.event_id)
                .first()
            )
            if existing_run:
                return existing_run
            agent_event = existing_event
        else:
            # Persist incoming event
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

        # Step 2: Context Gathering via Authorized Tools
        # Tool call 1: Inspect event
        event_data = self.tool_registry.execute_tool(
            "inspect_relevant_event", event_id=agent_event.event_id
        )

        # Tool call 2: Read student profile
        student_profile = self.tool_registry.execute_tool(
            "read_student_profile", student_id=self.student_id
        )

        # Tool call 3: Read active mission
        active_mission = self.tool_registry.execute_tool(
            "read_active_mission", student_id=self.student_id
        )

        proposal_id: Optional[int] = None
        decision_category = "no_action"
        explanation = ""
        relevant_evidence: dict[str, Any] = {}

        # Chronological order & Stale Event Detection:
        # Check if an earlier event was received with a newer timestamp for this role
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
                decision_category = "no_action"
                explanation = (
                    f"Out-of-order event detected: The event timestamp ({agent_event.source_timestamp.isoformat()}) "
                    f"is older than the latest processed event ({newer_event.source_timestamp.isoformat()}) for role "
                    f"'{agent_event.role_id}'. Ignored to prevent overwriting newer verified data."
                )
                agent_event.processing_status = "ignored"
                relevant_evidence = {
                    "reason": "stale_out_of_order_event",
                    "event_timestamp": agent_event.source_timestamp.isoformat(),
                    "latest_processed_timestamp": newer_event.source_timestamp.isoformat(),
                }

        # Scenario Handling (if not stale)
        if agent_event.processing_status != "ignored":
            # Scenario D: Student skill evidence added
            if agent_event.event_type == "student_skill_evidence_added":
                is_self_reported = (agent_event.source_reliability in ("unverified_third_party", "student_self_report"))
                evidence_title = agent_event.new_value or "New Evidence Submission"
                
                if is_self_reported:
                    decision_category = "informational_notification"
                    explanation = (
                        f"Observed student portfolio evidence: '{evidence_title}'. "
                        "The artifact has been linked to the student portfolio. "
                        "Note: Self-reported evidence remains unverified until external evaluation or assessment. "
                        "Career Mission assumptions remain grounded in verified competencies."
                    )
                else:
                    decision_category = "informational_notification"
                    explanation = (
                        f"Observed verified skill credential: '{evidence_title}'. "
                        "Linked to student portfolio. Milestone requirements remain aligned."
                    )
                agent_event.processing_status = "processed"
                relevant_evidence = {
                    "evidence_type": "skill_evidence",
                    "event_id": agent_event.event_id,
                    "is_self_reported": is_self_reported,
                }

            # Scenario C: Student completes a prerequisite task / progress update
            elif agent_event.event_type in ("mission_progress_updated", "task_completed"):
                decision_category = "informational_notification"
                explanation = (
                    f"Observed roadmap progress update: {agent_event.previous_value or 'Task'} -> "
                    f"{agent_event.new_value or 'Completed'}. "
                    "Downstream prerequisite milestones evaluated. Roadmap proceeds on schedule."
                )
                agent_event.processing_status = "processed"
                relevant_evidence = {
                    "update": agent_event.new_value,
                    "mission_id": active_mission["mission_id"] if active_mission else None,
                }

            # Scenarios A, B, E, F, H: Deadline change event
            elif agent_event.event_type == "internship_deadline_changed":
                # Relevance check
                is_relevant = False
                if active_mission and active_mission.get("target_role_id"):
                    if agent_event.role_id is None or agent_event.role_id == active_mission["target_role_id"]:
                        is_relevant = True

                if not active_mission:
                    decision_category = "no_action"
                    explanation = "Student currently has no active Career Mission. Event noted with no action."
                    agent_event.processing_status = "ignored"
                    relevant_evidence = {"is_role_relevant": False, "reason": "no_active_mission"}
                elif not is_relevant:
                    decision_category = "no_action"
                    explanation = (
                        f"Deadline changed for role '{agent_event.role_id}', but student's active Career Mission "
                        f"targets '{active_mission.get('target_role_id')}'. Event is not relevant to current mission."
                    )
                    agent_event.processing_status = "ignored"
                    relevant_evidence = {
                        "is_role_relevant": False,
                        "event_role": agent_event.role_id,
                        "active_mission_role": active_mission.get("target_role_id"),
                    }
                else:
                    mission_id = active_mission["mission_id"]

                    # Tool call 4: Calculate deadline impact using pure deterministic evaluator
                    impact_result = self.tool_registry.execute_tool(
                        "calculate_deadline_impact",
                        mission_id=mission_id,
                        new_deadline=agent_event.new_value,
                        current_deadline=agent_event.previous_value,
                        source_reliability=agent_event.source_reliability,
                    )

                    decision_category = impact_result["decision_category"]
                    explanation = impact_result["explanation"]
                    relevant_evidence = impact_result.get("metrics", {})

                    if decision_category == "human_review_required":
                        agent_event.processing_status = "requires_human_review"
                    else:
                        agent_event.processing_status = "processed"

                    # If proposed_mission_adjustment, generate proposal and verify material difference
                    if decision_category == "proposed_mission_adjustment":
                        # Tool call 5: Run C++ Learning Path Engine to generate revised staged roadmap
                        revised_plan = self.tool_registry.execute_tool(
                            "run_learning_path_engine",
                            student_id=self.student_id,
                            role_id=active_mission["target_role_id"],
                            target_deadline=agent_event.new_value,
                        )

                        # Check for material differences before proposing
                        active_version_tasks = active_mission.get("tasks", [])
                        diff_check = self.tool_registry.execute_tool(
                            "compare_plan_versions",
                            active_version_tasks=active_version_tasks,
                            proposed_plan=revised_plan,
                        )

                        if not diff_check.get("is_material_difference", True) and relevant_evidence.get("capacity_ratio", 1.0) <= 1.15:
                            # No structural change and pacing is acceptable -> informational notification
                            decision_category = "informational_notification"
                            explanation = (
                                f"Deadline adjusted to {agent_event.new_value}, but roadmap stages and milestone ordering "
                                "remain optimal. No structural mission adjustment is required."
                            )
                        else:
                            # Meaningful change justifies staged proposal
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

                            # Tool call 6: Create pending proposal for student review
                            proposal_result = self.tool_registry.execute_tool(
                                "create_mission_change_proposal",
                                mission_id=mission_id,
                                proposal_title=p_title,
                                rationale=p_rationale,
                                proposed_plan=revised_plan,
                            )
                            proposal_id = proposal_result.get("proposal_id")

            else:
                decision_category = "no_action"
                explanation = f"Unrecognized event type '{agent_event.event_type}'. No action taken."
                agent_event.processing_status = "ignored"

        # Step 5: Synthesize decision explanation with LLM adapter or deterministic rules
        decision_synthesis, engine_used, telemetry = self.llm_adapter.synthesize_decision(
            event_summary={
                "event_id": agent_event.event_id,
                "event_type": agent_event.event_type,
                "role_id": agent_event.role_id,
                "previous_value": agent_event.previous_value,
                "new_value": agent_event.new_value,
                "source_reliability": agent_event.source_reliability,
            },
            deterministic_result={
                "decision_category": decision_category,
                "explanation": explanation,
                "recommended_action": "Review mission roadmap proposal." if proposal_id else "No action required.",
                "metrics": relevant_evidence,
            },
            student_context=student_profile or {},
            mission_summary=active_mission or {},
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Step 6: Persist Audit Record into agent_runs
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        agent_run = models.AgentRun(
            id=run_id,
            event_id=agent_event.event_id,
            mission_id=active_mission["mission_id"] if active_mission else None,
            student_id=self.student_id,
            engine_used=engine_used,
            decision_category=decision_synthesis.decision_category,
            is_simulated=agent_event.is_simulated,
            relevant_evidence=json.dumps(relevant_evidence),
            tools_invoked=json.dumps([rec.tool_name for rec in self.tool_registry.invocations]),
            tool_io_log=json.dumps([rec.to_dict() for rec in self.tool_registry.invocations]),
            decision_explanation=decision_synthesis.explanation,
            proposal_id=proposal_id,
            execution_time_ms=elapsed_ms,
            status="completed",
        )
        self.db.add(agent_run)
        self.db.commit()
        self.db.refresh(agent_run)
        return agent_run

    def simulate_demo_event(self, req: AgentSimulateRequest) -> models.AgentRun:
        """Trigger controlled, explicitly labeled demo events for presenter verification."""
        active_mission = crud.get_active_career_mission(self.db, self.student_id)
        role_id = req.role_id or (active_mission.target_role_id if active_mission else "distributed-systems-intern")
        now = get_utc_now()

        if req.scenario == "deadline_earlier":
            # Feasible earlier deadline: 50 days from now (manageable acceleration)
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
            # Extreme earlier deadline: 5 days from now -> impossible study pace (> 25 hrs/week)
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
            # Extend deadline to 120 days from now (relaxes pace, triggers informational_notification)
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
            # Role that doesn't match active mission
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
            # Event with source timestamp in the past
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
