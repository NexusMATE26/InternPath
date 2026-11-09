"""Authorized tool registry for InternPath Agentic AI.

Enforces backend permission boundaries:
- Read-only queries for active student scope
- Pure computational engines (C++ graph solver, deadline calculator, diff analyzer, plan simulation)
- Staged write tool: creating a pending mission change proposal (NEVER auto-approving)
- Rejection of unauthorized actions (e.g., self-approval, direct mission mutation,
  cross-student access, application submission, skill level modification, arbitrary commands).
"""
import json
import uuid
from typing import Any, Callable, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app import crud, models
from app.agent.clock import get_utc_now, parse_datetime_safe
from app.agent.evaluator import calculate_deadline_metrics
from app.bridge import run_learning_path_with_graph
from app.schemas import (
    PlanVariantType,
    ValidityStatus,
    SimulatePlanVariantResponse,
    ComparePlanVariantsResponse,
    CheckPrerequisiteSafetyResponse,
    ToolDefinition,
)


class ToolPermissionError(PermissionError):
    """Raised when an agent attempts an unauthorized or forbidden action."""
    pass


class ToolExecutionRecord:
    def __init__(self, tool_name: str, sanitized_input: dict[str, Any], sanitized_output: Any):
        self.tool_name = tool_name
        self.sanitized_input = sanitized_input
        self.sanitized_output = sanitized_output

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "input": self.sanitized_input,
            "output": self.sanitized_output,
        }


class AgentToolRegistry:
    """Bounded, authenticated tool registry scoped to a specific student context."""

    FORBIDDEN_ACTIONS = {
        "approve_proposal": "Agent cannot approve proposals. Human student review is mandatory.",
        "activate_mission": "Agent cannot activate missions directly. Student consent required.",
        "modify_verified_skill": "Agent cannot alter verified skill levels.",
        "change_verified_skill": "Agent cannot alter verified skill levels.",
        "modify_mission_version": "Mission versions are immutable snapshots. Cannot modify directly.",
        "delete_evidence": "Agent cannot delete student portfolio evidence.",
        "submit_application": "Agent cannot submit job applications autonomously.",
        "bypass_human_consent": "Agent cannot activate revised roadmaps without explicit student consent.",
        "execute_command": "Arbitrary shell command execution is strictly forbidden.",
        "execute_sql": "Arbitrary SQL execution is strictly forbidden.",
        "arbitrary_shell": "Arbitrary shell command execution is strictly forbidden.",
        "arbitrary_sql": "Arbitrary SQL execution is strictly forbidden.",
    }

    def __init__(self, db: Session, context_student_id: int):
        self.db = db
        self.context_student_id = context_student_id
        self.invocations: list[ToolExecutionRecord] = []
        self.simulation_cache: dict[str, dict[str, Any]] = {}
        self._registry: dict[str, Callable[..., Any]] = {}
        self._register_authorized_tools()

    def _register_authorized_tools(self) -> None:
        self._registry = {
            "read_student_profile": self.read_student_profile,
            "read_active_mission": self.read_active_mission,
            "read_mission_progress": self.read_mission_progress,
            "read_target_role": self.read_target_role,
            "read_skill_requirements": self.read_skill_requirements,
            "inspect_relevant_event": self.inspect_relevant_event,
            "calculate_deadline_impact": self.calculate_deadline_impact,
            "estimate_remaining_effort": self.estimate_remaining_effort,
            "run_learning_path_engine": self.run_learning_path_engine,
            "compare_plan_versions": self.compare_plan_versions,
            "create_mission_change_proposal": self.create_mission_change_proposal,
            "simulate_plan_variant": self.simulate_plan_variant,
            "compare_plan_variants": self.compare_plan_variants,
            "check_prerequisite_safety": self.check_prerequisite_safety,
        }

    def get_registered_tool_names(self) -> list[str]:
        return list(self._registry.keys())

    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool with strict permission checking and audit logging."""
        # Enforce input size limit (16KB bound)
        try:
            serialized_input = json.dumps(kwargs, default=str)
            if len(serialized_input) > 16384:
                msg = f"Input size limit exceeded ({len(serialized_input)} bytes > 16384 bytes limit)."
                self.invocations.append(
                    ToolExecutionRecord(tool_name, {"input_size": len(serialized_input)}, {"error": "payload_too_large", "reason": msg})
                )
                raise ValueError(msg)
        except TypeError:
            pass

        if tool_name in self.FORBIDDEN_ACTIONS:
            msg = f"Forbidden tool '{tool_name}': {self.FORBIDDEN_ACTIONS[tool_name]}"
            self.invocations.append(
                ToolExecutionRecord(tool_name, kwargs, {"error": "forbidden", "reason": msg})
            )
            raise ToolPermissionError(msg)

        if tool_name not in self._registry:
            msg = f"Unauthorized or unknown tool: '{tool_name}'."
            self.invocations.append(
                ToolExecutionRecord(tool_name, kwargs, {"error": "unregistered", "reason": msg})
            )
            raise ToolPermissionError(msg)

        # Enforce student tenant boundary
        if "student_id" in kwargs and kwargs["student_id"] is not None and kwargs["student_id"] != self.context_student_id:
            msg = (
                f"Security violation: Agent is isolated to student ID {self.context_student_id}. "
                f"Attempted access to student ID {kwargs['student_id']} is forbidden."
            )
            self.invocations.append(
                ToolExecutionRecord(tool_name, kwargs, {"error": "boundary_violation", "reason": msg})
            )
            raise ToolPermissionError(msg)

        # Invoke authorized handler
        func = self._registry[tool_name]
        try:
            result = func(**kwargs)
            # Sanitize output for storage in audit log
            sanitized_out = self._sanitize_for_audit(result)
            self.invocations.append(
                ToolExecutionRecord(tool_name, self._sanitize_for_audit(kwargs), sanitized_out)
            )
            return result
        except (ToolPermissionError, ValueError):
            raise

        except Exception as exc:
            self.invocations.append(
                ToolExecutionRecord(
                    tool_name, self._sanitize_for_audit(kwargs), {"error": type(exc).__name__, "message": str(exc)}
                )
            )
            raise

    def _sanitize_for_audit(self, data: Any) -> Any:
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if k.lower() in ("password", "token", "secret", "api_key", "raw_prompt"):
                    continue
                clean[k] = self._sanitize_for_audit(v)
            return clean
        if isinstance(data, list):
            if len(data) > 10:
                # Compact long lists for readable audit logs
                return [self._sanitize_for_audit(x) for x in data[:10]] + [f"... ({len(data) - 10} more items)"]
            return [self._sanitize_for_audit(x) for x in data]
        if isinstance(data, (int, float, bool, type(None))):
            return data
        if isinstance(data, str):
            if len(data) > 500:
                return data[:500] + "... [truncated]"
            return data
        return str(data)

    # -----------------------------------------------------------------------
    # Authorized Read-Only Tools
    # -----------------------------------------------------------------------

    def read_student_profile(self, student_id: int) -> dict[str, Any]:
        """Fetch student profile, weekly commitment, and verified skills."""
        if student_id != self.context_student_id:
            raise ToolPermissionError(f"Access to student {student_id} forbidden.")

        student = self.db.query(models.Student).filter(models.Student.id == student_id).first()
        if not student:
            return {"error": f"Student {student_id} not found."}

        skills = crud.get_student_skills(self.db, student_id)
        evidence = crud.get_student_evidence(self.db, student_id)

        return {
            "student_id": student.id,
            "target_role_id": student.target_role_id,
            "weekly_hours": student.weekly_hours,
            "skills": [
                {
                    "skill_id": s["skill_id"],
                    "skill_name": s["skill_name"],
                    "declared_level": s["declared_level"],
                    "verified_level": s["verified_level"],
                    "is_verified": s["is_verified"],
                }
                for s in skills
            ],
            "evidence_count": len(evidence),
        }

    def read_active_mission(self, student_id: int) -> Optional[dict[str, Any]]:
        """Fetch current active Career Mission roadmap and active version details."""
        if student_id != self.context_student_id:
            raise ToolPermissionError(f"Access to student {student_id} forbidden.")

        mission = crud.get_active_career_mission(self.db, student_id)
        if not mission:
            return None

        formatted = crud.format_career_mission_dict(mission)
        active_v = formatted.get("active_version")

        tasks_summary = []
        if active_v:
            for t in active_v.get("tasks", []):
                tasks_summary.append({
                    "id": t["id"],
                    "skill_id": t["skill_id"],
                    "skill_name": t["skill_name"],
                    "stage_number": t["stage_number"],
                    "target_level": t["target_level"],
                    "status": t["status"],
                    "is_unlocked": t["is_unlocked"],
                    "estimated_hours_min": t.get("estimated_hours_min", 0),
                    "estimated_hours_max": t.get("estimated_hours_max", 0),
                })

        return {
            "mission_id": mission.id,
            "target_role_id": mission.target_role_id,
            "title": mission.title,
            "status": mission.status,
            "weekly_hours": mission.weekly_hours,
            "active_version_number": mission.active_version.version_number if mission.active_version else 1,
            "total_tasks": formatted["total_tasks"],
            "completed_tasks": formatted["completed_tasks"],
            "progress_percent": formatted["progress_percent"],
            "estimated_remaining_hours_min": formatted["estimated_remaining_hours_min"],
            "estimated_remaining_hours_max": formatted["estimated_remaining_hours_max"],
            "tasks": tasks_summary,
        }

    def read_mission_progress(self, mission_id: int) -> dict[str, Any]:
        """Fetch granular task completion and milestone metrics for an active mission."""
        mission = crud.get_career_mission_by_id(self.db, mission_id, self.context_student_id)
        if not mission:
            return {"error": f"Mission {mission_id} not found."}

        formatted = crud.format_career_mission_dict(mission)
        return {
            "mission_id": mission_id,
            "progress_percent": formatted["progress_percent"],
            "total_tasks": formatted["total_tasks"],
            "completed_tasks": formatted["completed_tasks"],
            "in_progress_tasks": formatted["in_progress_tasks"],
            "pending_proposals_count": formatted["pending_proposals_count"],
        }

    def read_target_role(self, role_id: str) -> dict[str, Any]:
        """Fetch role catalog data including department, location, and description."""
        role = crud.get_role_by_id(self.db, role_id)
        if not role:
            return {"error": f"Role '{role_id}' not found."}

        return {
            "role_id": role.role_id,
            "title": role.title,
            "department": role.department,
            "location": role.location,
            "description": role.description,
        }

    def read_skill_requirements(self, role_id: str) -> list[dict[str, Any]]:
        """Fetch competency requirements for a target internship role."""
        return crud.get_role_requirements(self.db, role_id)

    def inspect_relevant_event(self, event_id: str) -> dict[str, Any]:
        """Inspect detailed payload and provenance of an observed event."""
        ev = self.db.query(models.AgentEvent).filter(models.AgentEvent.event_id == event_id).first()
        if not ev:
            return {"error": f"Event {event_id} not found."}

        payload = {}
        if ev.payload:
            try:
                payload = json.loads(ev.payload)
            except Exception:
                payload = {}

        return {
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "source": ev.source,
            "source_timestamp": ev.source_timestamp.isoformat() if ev.source_timestamp else None,
            "role_id": ev.role_id,
            "previous_value": ev.previous_value,
            "new_value": ev.new_value,
            "source_reliability": ev.source_reliability,
            "evidence_reference": ev.evidence_reference,
            "processing_status": ev.processing_status,
            "is_simulated": ev.is_simulated,
            "payload": payload,
        }

    # -----------------------------------------------------------------------
    # Authorized Computational Tools
    # -----------------------------------------------------------------------

    def calculate_deadline_impact(
        self,
        mission_id: int,
        new_deadline: Optional[str],
        current_deadline: Optional[str] = None,
        source_reliability: str = "verified_employer",
        reference_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compute feasibility metrics and required pacing for a deadline change."""
        mission = crud.get_career_mission_by_id(self.db, mission_id, self.context_student_id)
        if not mission:
            return {"error": f"Mission {mission_id} not found."}

        student = mission.student
        weekly_hours = mission.weekly_hours or (student.weekly_hours if student else 10)

        # Read tasks from active version
        formatted = crud.format_career_mission_dict(mission)
        active_v = formatted.get("active_version")
        tasks = active_v.get("tasks", []) if active_v else []

        # Annotate mandatory requirements from role specification
        role_reqs = crud.get_role_requirements(self.db, mission.target_role_id) if mission.target_role_id else []
        mandatory_map = {r["skill_id"]: r["mandatory"] for r in role_reqs}

        remaining_tasks = []
        for t in tasks:
            if t.get("status") != "completed":
                t_copy = dict(t)
                t_copy["is_mandatory"] = mandatory_map.get(t.get("skill_id"), True)
                remaining_tasks.append(t_copy)

        ref_dt = parse_datetime_safe(reference_date) if reference_date else get_utc_now()

        return calculate_deadline_metrics(
            current_deadline=current_deadline,
            new_deadline=new_deadline,
            weekly_hours=weekly_hours,
            remaining_tasks=remaining_tasks,
            total_tasks_count=len(tasks),
            completed_tasks_count=len(tasks) - len(remaining_tasks),
            source_reliability=source_reliability,
            is_role_relevant=True,
            mission_status=mission.status,
            reference_date=ref_dt,
        )

    def estimate_remaining_effort(self, mission_id: int) -> dict[str, Any]:
        """Estimate remaining effort hours for incomplete tasks."""
        mission = crud.get_career_mission_by_id(self.db, mission_id, self.context_student_id)
        if not mission:
            return {"error": f"Mission {mission_id} not found."}

        formatted = crud.format_career_mission_dict(mission)
        return {
            "mission_id": mission_id,
            "estimated_remaining_hours_min": formatted["estimated_remaining_hours_min"],
            "estimated_remaining_hours_max": formatted["estimated_remaining_hours_max"],
            "estimated_remaining_hours_avg": round(
                (formatted["estimated_remaining_hours_min"] + formatted["estimated_remaining_hours_max"]) / 2.0, 1
            ),
            "completed_tasks": formatted["completed_tasks"],
            "total_tasks": formatted["total_tasks"],
        }

    def run_learning_path_engine(
        self,
        student_id: int,
        role_id: str,
        target_deadline: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run C++20 LearningPathEngine graph solver to generate a staged roadmap."""
        if student_id != self.context_student_id:
            raise ToolPermissionError(f"Access to student {student_id} forbidden.")

        all_skills = crud.get_skills(self.db)
        all_prereqs = crud.get_all_prerequisites(self.db)
        student_skills = crud.get_student_skills(self.db, student_id)
        role_reqs = crud.get_role_requirements(self.db, role_id)

        target_skills_list = [
            {"skill_id": r["skill_id"], "required_level": r["required_level"]}
            for r in role_reqs
        ]
        student_skills_list = [
            {"skill_id": s["skill_id"], "level": s["declared_level"], "is_verified": s["is_verified"]}
            for s in student_skills
        ]

        plan = run_learning_path_with_graph(
            skills=all_skills,
            prerequisites=all_prereqs,
            targets=target_skills_list,
            student=student_skills_list,
        )
        return plan.model_dump()

    def compare_plan_versions(
        self,
        active_version_tasks: list[dict[str, Any]],
        proposed_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute structured diff summary between current roadmap and candidate plan."""
        active_keys = {t["stable_key"]: t for t in active_version_tasks if "stable_key" in t}

        proposed_keys = {}
        for stage in proposed_plan.get("stages", []):
            stage_num = stage.get("stage_number", 1)
            for sk in stage.get("skills", []):
                key = f"skill_{sk['skill_id']}_lvl_{sk['target_level']}"
                proposed_keys[key] = {**sk, "stage_number": stage_num}

        added = [k for k in proposed_keys if k not in active_keys]
        removed = [k for k in active_keys if k not in proposed_keys]
        retained = []
        rescheduled = []

        for k, a in active_keys.items():
            if k in proposed_keys:
                p = proposed_keys[k]
                is_resched = a.get("stage_number") != p.get("stage_number")
                item = {
                    "stable_key": k,
                    "skill_id": a.get("skill_id"),
                    "skill_name": a.get("skill_name"),
                    "previous_stage": a.get("stage_number"),
                    "new_stage": p.get("stage_number"),
                }
                if is_resched:
                    rescheduled.append(item)
                else:
                    retained.append(item)

        is_material = len(added) > 0 or len(removed) > 0 or len(rescheduled) > 0

        return {
            "is_material_difference": is_material,
            "added_tasks_count": len(added),
            "removed_tasks_count": len(removed),
            "rescheduled_tasks_count": len(rescheduled),
            "retained_tasks_count": len(retained),
            "added_keys": added,
            "removed_keys": removed,
            "rescheduled": rescheduled,
        }

    # -----------------------------------------------------------------------
    # Authorized Write-Limited Tool: Stage Change Proposal
    # -----------------------------------------------------------------------

    def create_mission_change_proposal(
        self,
        mission_id: int,
        proposal_title: str,
        rationale: str,
        proposed_plan: Optional[dict[str, Any]] = None,
        simulation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Stage a pending mission change proposal.

        CRITICAL SAFETY BOUNDARY:
        1. This tool creates a proposal in 'pending' status for human student review.
        2. It NEVER automatically approves the proposal or mutates the active mission version.
        3. Model arguments alone cannot authorize arbitrary plan snapshots.
           The proposal MUST be backed by an executed, valid simulation or deterministically
           validated against completed work preservation and mandatory role requirements.
        """
        # 1. Enforce student tenant boundary
        mission = crud.get_career_mission_by_id(self.db, mission_id, self.context_student_id)
        if not mission:
            raise ToolPermissionError(f"Access denied: Mission {mission_id} does not belong to active student {self.context_student_id}.")

        active_v = mission.active_version
        if not active_v:
            raise ToolPermissionError("Cannot stage proposal: Mission has no active version.")

        plan_to_stage: Optional[dict[str, Any]] = None

        # 2. Case A: Staged via executed simulation ID
        if simulation_id:
            if simulation_id not in self.simulation_cache:
                raise ToolPermissionError(
                    f"Proposal rejected: simulation_id '{simulation_id}' is invalid or was not executed by this agent session."
                )
            sim_data = self.simulation_cache[simulation_id]
            if sim_data.get("mission_id") != mission.id:
                raise ToolPermissionError(
                    f"Proposal rejected: simulation '{simulation_id}' was generated for mission {sim_data.get('mission_id')}, not {mission.id}."
                )
            if sim_data.get("validity_status") == ValidityStatus.INVALID.value:
                raise ToolPermissionError(
                    f"Proposal rejected: cannot stage proposal from simulation '{simulation_id}' because C++ planner evaluated it as INVALID."
                )
            plan_to_stage = sim_data.get("proposed_plan_snapshot")
            if not plan_to_stage:
                raise ValueError(f"Simulation '{simulation_id}' does not contain a proposed plan snapshot.")

        # 3. Case B: Proposed plan dict provided directly
        elif proposed_plan:
            # Deterministic plan snapshot validation
            # A) Completed task preservation: All tasks with status 'completed' in active_v MUST exist in proposed_plan
            active_completed_tasks = [t for t in active_v.tasks if t.status == "completed"]
            proposed_skill_levels: dict[int, int] = {}
            for stage in proposed_plan.get("stages", []):
                for sk in stage.get("skills", []):
                    sid = sk.get("skill_id")
                    lvl = sk.get("target_level", 0)
                    if sid is not None:
                        proposed_skill_levels[sid] = max(proposed_skill_levels.get(sid, 0), lvl)

            if active_completed_tasks:
                for ct in active_completed_tasks:
                    if ct.skill_id not in proposed_skill_levels or proposed_skill_levels[ct.skill_id] < ct.target_level:
                        raise ToolPermissionError(
                            f"Proposal rejected: Proposed plan violates completed work preservation invariant. "
                            f"Completed milestone '{ct.skill_name}' (target level {ct.target_level}) is omitted or degraded."
                        )

            # B) Mandatory requirement preservation
            if mission.target_role_id and proposed_skill_levels:
                role_reqs = crud.get_role_requirements(self.db, mission.target_role_id)
                mandatory_reqs = [r for r in role_reqs if r.get("mandatory", True)]
                if len(proposed_skill_levels) >= len(mandatory_reqs):
                    for mr in mandatory_reqs:
                        if mr["skill_id"] not in proposed_skill_levels:
                            raise ToolPermissionError(
                                f"Proposal rejected: Proposed plan omits mandatory core role competency (skill ID {mr['skill_id']})."
                            )

            plan_to_stage = proposed_plan

        # 4. Case C: Neither supplied, fallback to latest valid executed simulation if available
        else:
            if self.simulation_cache:
                valid_sims = [s for s in self.simulation_cache.values() if s.get("validity_status") != ValidityStatus.INVALID.value]
                if valid_sims:
                    plan_to_stage = valid_sims[-1].get("proposed_plan_snapshot")
                else:
                    raise ToolPermissionError("Cannot stage proposal: all executed simulations were evaluated as INVALID by C++ engine.")
            else:
                raise ToolPermissionError(
                    "Cannot stage proposal: neither a valid simulation_id nor a validated proposed_plan was provided."
                )

        proposal = crud.create_mission_change_proposal(
            db=self.db,
            mission_id=mission.id,
            student_id=self.context_student_id,
            proposal_title=proposal_title,
            rationale=rationale,
            proposed_plan=plan_to_stage,
            proposed_by="agent_planner",
        )
        return {
            "proposal_id": proposal.id,
            "mission_id": proposal.mission_id,
            "proposal_title": proposal.proposal_title,
            "status": proposal.status,
            "base_version_number": proposal.base_version_number,
            "human_approval_required": True,
            "message": "Proposal successfully staged for human review. Active mission remains unchanged until student approves.",
        }

    # -----------------------------------------------------------------------
    # Authorized Computational Tool: Plan Variant Simulation (R2.1)
    # -----------------------------------------------------------------------

    def simulate_plan_variant(
        self,
        variant_type: str | PlanVariantType,
        weekly_hours: Optional[int] = None,
        target_date: Optional[str] = None,
        defer_optional_skills: bool = False,
        temporary_availability_overrides: Optional[dict[str, Any]] = None,
        rationale: Optional[str] = None,
        mission_id: Optional[int] = None,
        student_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Evaluate a potential adjustment to an existing Career Mission WITHOUT changing the approved mission.

        CRITICAL ARCHITECTURAL INVARIANTS:
        1. Pure counterfactual simulation: zero database writes, mutations, or side-effects.
        2. Student scoping: strictly bound to server-authenticated student context.
        3. Completed work preservation: completed tasks and acquired competencies remain intact.
        4. C++ graph engine validation: prerequisite ordering and Kahn cycle detection use native engine.
        5. Workload feasibility: distinguishes VALID_AND_FEASIBLE from VALID_BUT_INFEASIBLE.
        """
        # 1. Enforce student tenant boundary
        if student_id is not None and student_id != self.context_student_id:
            raise ToolPermissionError(f"Access to student {student_id} forbidden. Context is {self.context_student_id}.")

        # 2. Retrieve active mission and active version
        if mission_id is not None:
            mission = crud.get_career_mission_by_id(self.db, mission_id, self.context_student_id)
            if not mission:
                raise ValueError(f"Mission {mission_id} not found or does not belong to active student.")
        else:
            mission = crud.get_active_career_mission(self.db, self.context_student_id)
            if not mission:
                raise ValueError(f"Student {self.context_student_id} does not have an active career mission.")

        active_version = mission.active_version
        if not active_version:
            raise ValueError(f"Mission {mission.id} has no approved active version.")

        # 3. Validate variant type
        try:
            raw_val = variant_type.value if hasattr(variant_type, "value") else str(variant_type)
            v_type = PlanVariantType(str(raw_val).lower())
        except ValueError:
            valid_types = [e.value for e in PlanVariantType]
            raise ValueError(f"Unknown variant type '{variant_type}'. Supported variant types: {valid_types}")


        # 4. Validate weekly hours
        if weekly_hours is not None:
            if not isinstance(weekly_hours, int) or weekly_hours < 1 or weekly_hours > 80:
                raise ValueError(f"weekly_hours must be an integer between 1 and 80. Received: {weekly_hours}")
            effective_weekly_hours = weekly_hours
        else:
            effective_weekly_hours = mission.weekly_hours or (mission.student.weekly_hours if mission.student else 10)

        # 5. Validate temporary availability overrides if present
        override_desc = ""
        if temporary_availability_overrides:
            if not isinstance(temporary_availability_overrides, dict):
                raise ValueError("temporary_availability_overrides must be a dictionary.")
            override_h = temporary_availability_overrides.get("override_hours")
            override_w = temporary_availability_overrides.get("weeks", 1)
            if override_h is not None:
                if not isinstance(override_h, int) or override_h < 1 or override_h > 80:
                    raise ValueError(f"override_hours must be an integer between 1 and 80. Received: {override_h}")
                if not isinstance(override_w, int) or override_w < 1 or override_w > 52:
                    raise ValueError(f"override weeks must be an integer between 1 and 52. Received: {override_w}")
                effective_weekly_hours = override_h
                override_desc = f" (temporary override: {override_h} hrs/week for {override_w} week(s))"

        # 6. Validate target date if present
        target_dt = None
        days_remaining = None
        weeks_remaining = None
        if target_date is not None:
            target_dt = parse_datetime_safe(str(target_date))
            if not target_dt:
                raise ValueError(f"Invalid target_date format: '{target_date}'. Expected ISO format (YYYY-MM-DD).")
            now = get_utc_now()
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
            if target_dt <= now:
                raise ValueError(f"target_date '{target_date}' is in the past. Simulation requires a future date.")
            days_remaining = max(1, (target_dt.date() - now.date()).days)
            weeks_remaining = max(0.14, round(days_remaining / 7.0, 2))

        # 7. Retrieve curriculum graph and role requirements
        all_skills = crud.get_skills(self.db)
        all_prereqs = crud.get_all_prerequisites(self.db)
        role_reqs = crud.get_role_requirements(self.db, mission.target_role_id) if mission.target_role_id else []

        mandatory_reqs = [r for r in role_reqs if r.get("mandatory", True)]
        optional_reqs = [r for r in role_reqs if not r.get("mandatory", True)]
        mandatory_skill_ids = {r["skill_id"] for r in mandatory_reqs}
        optional_skill_ids = {r["skill_id"] for r in optional_reqs}

        # Build reverse adjacency for prerequisite closure: skill -> set of prerequisites
        prereq_graph: dict[int, set[int]] = {}
        for p_id, s_id in all_prereqs:
            prereq_graph.setdefault(s_id, set()).add(p_id)

        # Compute transitive prerequisites of all mandatory skills
        mandatory_closure: set[int] = set()
        stack = list(mandatory_skill_ids)
        while stack:
            curr = stack.pop()
            for p in prereq_graph.get(curr, set()):
                if p not in mandatory_closure:
                    mandatory_closure.add(p)
                    stack.append(p)

        should_defer_optional = defer_optional_skills or (v_type == PlanVariantType.DEFER_OPTIONAL)
        deferred_optional_ids: list[int] = []
        warnings: list[str] = []

        if should_defer_optional:
            for opt_id in optional_skill_ids:
                if opt_id in mandatory_closure:
                    warnings.append(
                        f"Elective skill ID {opt_id} is a structural prerequisite for a mandatory core requirement and cannot be deferred."
                    )
                else:
                    deferred_optional_ids.append(opt_id)

        targets_to_plan = []
        for r in role_reqs:
            if r["skill_id"] in deferred_optional_ids:
                continue
            targets_to_plan.append({
                "skill_id": r["skill_id"],
                "required_level": r["required_level"],
                "role_context": r.get("role_context", "Role requirement"),
                "mandatory": r.get("mandatory", True),
            })

        # 8. Completed work preservation: treat completed tasks as mastered
        student_skills_db = crud.get_student_skills(self.db, self.context_student_id)
        active_version_tasks = list(active_version.tasks)
        completed_active_tasks = [t for t in active_version_tasks if t.status == "completed"]

        completed_levels: dict[int, int] = {}
        for t in completed_active_tasks:
            completed_levels[t.skill_id] = max(completed_levels.get(t.skill_id, 0), t.target_level)

        student_skill_map = {s["skill_id"]: dict(s) for s in student_skills_db}
        for sid, lvl in completed_levels.items():
            if sid in student_skill_map:
                student_skill_map[sid]["declared_level"] = max(student_skill_map[sid]["declared_level"], lvl)
                student_skill_map[sid]["verified_level"] = max(student_skill_map[sid]["verified_level"], lvl)
            else:
                student_skill_map[sid] = {
                    "skill_id": sid,
                    "declared_level": lvl,
                    "verified_level": lvl,
                    "is_verified": True,
                }

        student_skills_input = [
            {
                "skill_id": s["skill_id"],
                "level": s["declared_level"],
                "is_verified": s.get("is_verified", False),
            }
            for s in student_skill_map.values()
        ]

        # 9. Execute native C++20 LearningPathEngine graph solver
        plan_response = run_learning_path_with_graph(
            skills=all_skills,
            prerequisites=all_prereqs,
            targets=targets_to_plan,
            student=student_skills_input,
        )
        plan_dict = plan_response.model_dump()

        # 10. Evaluate feasibility, workload pacing, and graph validity
        prereq_valid = plan_response.achievable
        feasibility_limitations: list[str] = []

        if not prereq_valid:
            validity_status = ValidityStatus.INVALID
            feasibility_assessment = f"Invalid: C++ engine dependency validation failed: {plan_response.message}"
            feasibility_limitations.append(plan_response.message)
            rem_min = 0
            rem_max = 0
            est_weeks_min = 0.0
            est_weeks_max = 0.0
        else:
            effort = plan_response.total_estimated_effort
            rem_min = effort.min_hours
            rem_max = effort.max_hours
            est_weeks_min = round(rem_min / effective_weekly_hours, 1) if effective_weekly_hours > 0 else 0.0
            est_weeks_max = round(rem_max / effective_weekly_hours, 1) if effective_weekly_hours > 0 else 0.0

            if target_dt and weeks_remaining is not None:
                required_weekly_hours = round(rem_max / max(weeks_remaining, 0.14), 1)
                capacity_ratio = round(required_weekly_hours / effective_weekly_hours, 2)
                if capacity_ratio <= 1.0 and required_weekly_hours <= 25.0:
                    validity_status = ValidityStatus.VALID_AND_FEASIBLE
                    feasibility_assessment = (
                        f"Feasible: Remaining effort ({rem_min}-{rem_max}h) requires {required_weekly_hours} hrs/week "
                        f"across {weeks_remaining:.1f} weeks, well within available {effective_weekly_hours} hrs/week "
                        f"(capacity ratio {capacity_ratio:.2f}){override_desc}."
                    )
                else:
                    validity_status = ValidityStatus.VALID_BUT_INFEASIBLE
                    reasons = []
                    if capacity_ratio > 1.0:
                        reasons.append(
                            f"Required pacing of {required_weekly_hours} hrs/week exceeds available {effective_weekly_hours} hrs/week "
                            f"(capacity ratio {capacity_ratio:.2f})"
                        )
                    if required_weekly_hours > 25.0:
                        reasons.append(
                            f"Required pacing of {required_weekly_hours} hrs/week exceeds recommended undergraduate ceiling of 25 hrs/week"
                        )
                    feasibility_assessment = f"Infeasible against target date: {'; '.join(reasons)}."
                    feasibility_limitations.extend(reasons)
            else:
                if effective_weekly_hours > 25:
                    warnings.append(
                        f"Declared weekly availability of {effective_weekly_hours}h exceeds recommended 25h/week undergraduate study threshold."
                    )
                validity_status = ValidityStatus.VALID_AND_FEASIBLE
                feasibility_assessment = (
                    f"Workload feasible: Estimated {est_weeks_min} to {est_weeks_max} weeks at "
                    f"{effective_weekly_hours} hrs/week to complete remaining {rem_min}-{rem_max} hours{override_desc}."
                )

        # 11. Compute structured delta against approved active version
        diff = crud.compute_proposal_diff(active_version, plan_dict)

        tasks_summary = {
            "retained": len(diff.get("retained_tasks", [])),
            "rescheduled": len(diff.get("rescheduled_tasks", [])),
            "deferred": len(deferred_optional_ids),
            "added": len(diff.get("added_tasks", [])),
            "completed_preserved": len(completed_active_tasks),
        }

        sim_id = f"sim_{mission.id}_v{active_version.version_number}_{uuid.uuid4().hex[:8]}"

        comparison_summary = (
            f"Simulated variant '{v_type.value}': {validity_status.value}. "
            f"Remaining effort {rem_min}-{rem_max}h (runway {est_weeks_min}-{est_weeks_max} wks at {effective_weekly_hours}h/wk). "
            f"Deferred {len(deferred_optional_ids)} elective(s). Completed work ({len(completed_active_tasks)} tasks) fully preserved."
        )

        res = {
            "simulation_id": sim_id,
            "mission_id": mission.id,
            "base_version_number": active_version.version_number,
            "variant_type": v_type.value,
            "validity_status": validity_status.value,
            "feasibility_assessment": feasibility_assessment,
            "feasibility_limitations": feasibility_limitations,
            "mandatory_requirements_preserved": True,
            "optional_requirements_deferred": deferred_optional_ids,
            "prerequisite_validity": prereq_valid,
            "completed_work_preserved": True,
            "tasks_summary": tasks_summary,
            "estimated_remaining_hours_min": rem_min,
            "estimated_remaining_hours_max": rem_max,
            "permitted_weekly_hours": effective_weekly_hours,
            "estimated_weeks_range": (est_weeks_min, est_weeks_max),
            "proposed_plan_snapshot": plan_dict,
            "diff_summary": diff,
            "comparison_summary": comparison_summary,
            "validation_warnings": warnings,
            "engine_identity": "c++20_learning_path_engine",
            "trace_reference": plan_dict.get("algorithm_trace"),
        }
        self.simulation_cache[sim_id] = res
        return res

    # -----------------------------------------------------------------------
    # Authorized Computational Tool: Alternative Comparison (R2.1)
    # -----------------------------------------------------------------------

    def compare_plan_variants(
        self,
        simulations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare two or more simulation results across feasibility, effort, and trade-offs.

        Guarantees:
        1. Requires at least 2 simulation snapshots.
        2. Rejects cross-student simulation comparisons (tenant boundary enforcement).
        3. Rejects incompatible variants across different career missions.
        4. Rejects comparisons across different base version numbers.
        5. Detects and rejects stale simulation versions against active mission version.
        """
        if not simulations or len(simulations) < 2:
            raise ValueError("compare_plan_variants requires at least two simulation results to compare.")

        # 1. Validate tenant boundaries and mission consistency
        mission_ids = {s.get("mission_id") for s in simulations if s.get("mission_id") is not None}
        if len(mission_ids) > 1:
            raise ValueError(f"Incompatible variants: cannot compare simulations across different missions: {sorted(list(mission_ids))}")

        if mission_ids:
            target_mission_id = next(iter(mission_ids))
            mission = crud.get_career_mission_by_id(self.db, target_mission_id, self.context_student_id)
            if not mission:
                raise ToolPermissionError(
                    f"Security violation: simulation mission {target_mission_id} does not belong to active student {self.context_student_id}."
                )

            # Check version consistency across variants
            base_versions = {s.get("base_version_number") for s in simulations if s.get("base_version_number") is not None}
            if len(base_versions) > 1:
                raise ValueError(
                    f"Incompatible variants: cannot compare simulations across different base versions: {sorted(list(base_versions))}"
                )

            # Check for stale simulation versions against active mission version
            if base_versions and mission.active_version:
                sim_version = next(iter(base_versions))
                if sim_version != mission.active_version.version_number:
                    raise ValueError(
                        f"Stale simulation detected: simulation was generated against mission version {sim_version}, "
                        f"but active mission is currently version {mission.active_version.version_number}."
                    )

        tradeoff_analysis: list[dict[str, Any]] = []
        feasible_candidates: list[str] = []

        for sim in simulations:
            v_type = sim.get("variant_type", "unknown")
            status = sim.get("validity_status", "UNKNOWN")
            rem_min = sim.get("estimated_remaining_hours_min", 0)
            rem_max = sim.get("estimated_remaining_hours_max", 0)
            weeks_range = sim.get("estimated_weeks_range", (0.0, 0.0))
            deferred = sim.get("optional_requirements_deferred", [])
            limitations = sim.get("feasibility_limitations", [])

            tradeoff_notes: list[str] = []
            if status == ValidityStatus.VALID_AND_FEASIBLE.value:
                feasible_candidates.append(v_type)
                tradeoff_notes.append("Workload is within available weekly capacity.")
            elif status == ValidityStatus.VALID_BUT_INFEASIBLE.value:
                tradeoff_notes.append(f"Workload exceeds capacity: {'; '.join(limitations)}")
            elif status == ValidityStatus.INVALID.value:
                tradeoff_notes.append("Prerequisite graph invalid or cycle detected.")

            if deferred:
                tradeoff_notes.append(f"Defers {len(deferred)} elective skill(s) (IDs: {deferred}).")
            else:
                tradeoff_notes.append("Preserves all role requirements including electives.")

            tradeoff_analysis.append({
                "variant_type": v_type,
                "validity_status": status,
                "estimated_remaining_hours_range": (rem_min, rem_max),
                "estimated_weeks_range": tuple(weeks_range) if isinstance(weeks_range, (list, tuple)) else (0.0, 0.0),
                "deferred_optional_count": len(deferred),
                "tradeoff_notes": tradeoff_notes,
            })

        matrix = {
            "variants": [s.get("variant_type") for s in simulations],
            "validity_statuses": [s.get("validity_status") for s in simulations],
            "remaining_hours_min": [s.get("estimated_remaining_hours_min") for s in simulations],
            "remaining_hours_max": [s.get("estimated_remaining_hours_max") for s in simulations],
            "deferred_optional_counts": [len(s.get("optional_requirements_deferred", [])) for s in simulations],
        }

        if feasible_candidates:
            rationale = (
                f"{len(feasible_candidates)} of {len(simulations)} variants are feasible ({', '.join(feasible_candidates)}). "
                "Tradeoffs between workload reduction and elective competency coverage are transparently detailed."
            )
        else:
            rationale = "None of the evaluated variants are currently feasible under specified constraints."

        return {
            "total_variants_compared": len(simulations),
            "feasible_variants_count": len(feasible_candidates),
            "recommended_candidates": feasible_candidates,
            "tradeoff_analysis": tradeoff_analysis,
            "comparison_matrix": matrix,
            "recommendation_rationale": rationale,
        }

    # -----------------------------------------------------------------------
    # Authorized Computational Tool: Prerequisite Safety Check (R2.1)
    # -----------------------------------------------------------------------

    def check_prerequisite_safety(
        self,
        target_skills: list[int],
        completed_skills: Optional[list[int]] = None,
    ) -> dict[str, Any]:
        """Validate whether target skills and completed skills form a cycle-free DAG and identify missing prerequisites."""
        if not target_skills:
            raise ValueError("target_skills cannot be empty.")

        all_skills = crud.get_skills(self.db)
        skill_id_map = {s["id"]: s for s in all_skills}
        for sid in target_skills:
            if sid not in skill_id_map:
                raise ValueError(f"Target skill ID {sid} does not exist in skill catalog.")

        completed_set = set(completed_skills or [])
        for sid in completed_set:
            if sid not in skill_id_map:
                raise ValueError(f"Completed skill ID {sid} does not exist in skill catalog.")

        all_prereqs = crud.get_all_prerequisites(self.db)

        # Build prerequisite map: skill_id -> list of prereq_ids
        prereq_map: dict[int, list[int]] = {}
        for p_id, s_id in all_prereqs:
            prereq_map.setdefault(s_id, []).append(p_id)

        # BFS to find prerequisite closure of target_skills
        closure: set[int] = set()
        missing_prereqs: list[dict[str, Any]] = []
        queue = list(target_skills)
        visited = set()

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            for p_id in prereq_map.get(curr, []):
                closure.add(p_id)
                if p_id not in completed_set and p_id not in target_skills:
                    p_skill = skill_id_map.get(p_id)
                    missing_prereqs.append({
                        "prerequisite_skill_id": p_id,
                        "prerequisite_name": p_skill["name"] if p_skill else f"Skill {p_id}",
                        "required_for_skill_id": curr,
                        "required_for_name": skill_id_map.get(curr, {}).get("name", f"Skill {curr}"),
                    })
                if p_id not in visited:
                    queue.append(p_id)

        # Run C++ engine to verify cycle freedom
        targets_input = [{"skill_id": sid, "required_level": 1} for sid in target_skills]
        student_input = [{"skill_id": sid, "level": 1, "is_verified": True} for sid in completed_set]
        try:
            plan = run_learning_path_with_graph(
                skills=all_skills,
                prerequisites=all_prereqs,
                targets=targets_input,
                student=student_input,
            )
            has_cycle = not plan.achievable and "cycle" in plan.message.lower()
            is_safe = plan.achievable
            details = plan.message
        except Exception as exc:
            has_cycle = "cycle" in str(exc).lower()
            is_safe = False
            details = str(exc)

        return {
            "is_safe": is_safe,
            "has_cycle": has_cycle,
            "missing_prerequisites": missing_prereqs,
            "prerequisite_closure": sorted(list(closure)),
            "details": details,
        }

    # -----------------------------------------------------------------------
    # Provider-Neutral Tool Registry & Schema Declarations (R2.1 / R2.2)
    # -----------------------------------------------------------------------

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Return provider-neutral definitions for all authorized tools."""
        return [
            ToolDefinition(
                name="read_student_profile",
                description="Fetch student profile, weekly commitment, and verified skills for the active authenticated student.",
                parameters={
                    "type": "object",
                    "properties": {
                        "student_id": {"type": "integer", "description": "Student ID (must match active student context)"}
                    },
                    "required": ["student_id"],
                },
                returns={"type": "object", "properties": {"student_id": {"type": "integer"}, "target_role_id": {"type": "string"}, "weekly_hours": {"type": "integer"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="read_active_mission",
                description="Fetch the active Career Mission roadmap and active version details for the active authenticated student.",
                parameters={
                    "type": "object",
                    "properties": {
                        "student_id": {"type": "integer", "description": "Student ID"}
                    },
                    "required": ["student_id"],
                },
                returns={"type": "object", "properties": {"mission_id": {"type": "integer"}, "target_role_id": {"type": "string"}, "title": {"type": "string"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="read_mission_progress",
                description="Fetch granular task completion and milestone metrics for an active Career Mission.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "integer", "description": "Career Mission ID"}
                    },
                    "required": ["mission_id"],
                },
                returns={"type": "object", "properties": {"mission_id": {"type": "integer"}, "progress_percent": {"type": "number"}, "completed_tasks": {"type": "integer"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="read_target_role",
                description="Fetch role catalog data including department, location, and description.",
                parameters={
                    "type": "object",
                    "properties": {
                        "role_id": {"type": "string", "description": "Target internship role identifier"}
                    },
                    "required": ["role_id"],
                },
                returns={"type": "object", "properties": {"role_id": {"type": "string"}, "title": {"type": "string"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="read_skill_requirements",
                description="Fetch competency requirements (mandatory core and preferred electives) for a target internship role.",
                parameters={
                    "type": "object",
                    "properties": {
                        "role_id": {"type": "string", "description": "Target internship role identifier"}
                    },
                    "required": ["role_id"],
                },
                returns={"type": "array", "items": {"type": "object", "properties": {"skill_id": {"type": "integer"}, "required_level": {"type": "integer"}, "mandatory": {"type": "boolean"}}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="inspect_relevant_event",
                description="Inspect detailed payload and provenance of an observed career environment event.",
                parameters={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Unique event identifier"}
                    },
                    "required": ["event_id"],
                },
                returns={"type": "object", "properties": {"event_id": {"type": "string"}, "event_type": {"type": "string"}, "source_reliability": {"type": "string"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="calculate_deadline_impact",
                description="Compute feasibility metrics, required pacing, and capacity ratio for a deadline change.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "integer", "description": "Career Mission ID"},
                        "new_deadline": {"type": "string", "description": "New deadline in ISO format (YYYY-MM-DD)"},
                        "current_deadline": {"type": "string", "description": "Previous deadline if available"},
                        "source_reliability": {"type": "string", "description": "Reliability rating of deadline source"},
                    },
                    "required": ["mission_id", "new_deadline"],
                },
                returns={"type": "object", "properties": {"is_feasible": {"type": "boolean"}, "decision_category": {"type": "string"}, "capacity_ratio": {"type": "number"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="estimate_remaining_effort",
                description="Estimate remaining effort hours for incomplete tasks in the active mission.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "integer", "description": "Career Mission ID"}
                    },
                    "required": ["mission_id"],
                },
                returns={"type": "object", "properties": {"estimated_remaining_hours_min": {"type": "integer"}, "estimated_remaining_hours_max": {"type": "integer"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="run_learning_path_engine",
                description="Run C++20 LearningPathEngine graph solver to generate a staged roadmap.",
                parameters={
                    "type": "object",
                    "properties": {
                        "student_id": {"type": "integer", "description": "Student ID"},
                        "role_id": {"type": "string", "description": "Target role ID"},
                        "target_deadline": {"type": "string", "description": "Target deadline if specified"},
                    },
                    "required": ["student_id", "role_id"],
                },
                returns={"type": "object", "properties": {"achievable": {"type": "boolean"}, "stages": {"type": "array"}, "total_estimated_effort": {"type": "object"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="compare_plan_versions",
                description="Compute structured diff summary between current roadmap and candidate plan.",
                parameters={
                    "type": "object",
                    "properties": {
                        "active_version_tasks": {
                            "type": "array",
                            "items": {"type": "object", "properties": {}},
                            "description": "Tasks from active version",
                        },
                        "proposed_plan": {"type": "object", "description": "Proposed plan dict from planner engine"},
                    },
                    "required": ["active_version_tasks", "proposed_plan"],
                },
                returns={"type": "object", "properties": {"is_material_difference": {"type": "boolean"}, "added_tasks_count": {"type": "integer"}, "removed_tasks_count": {"type": "integer"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="create_mission_change_proposal",
                description="Stage a pending mission change proposal for human student review. NEVER auto-approves. Must reference a valid simulation_id or provide a validated plan preserving completed work.",
                parameters={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "integer", "description": "Career Mission ID"},
                        "proposal_title": {"type": "string", "description": "Descriptive proposal title"},
                        "rationale": {"type": "string", "description": "Reasoning for the proposed plan adjustment"},
                        "simulation_id": {"type": "string", "description": "Optional authoritative simulation ID from simulate_plan_variant"},
                        "proposed_plan": {"type": "object", "description": "Optional complete staged plan dict (must preserve all completed tasks)"},
                    },
                    "required": ["mission_id", "proposal_title", "rationale"],
                },
                returns={"type": "object", "properties": {"proposal_id": {"type": "integer"}, "status": {"type": "string"}, "human_approval_required": {"type": "boolean"}}},
                permission_tier="proposal_stage",
            ),
            ToolDefinition(
                name="simulate_plan_variant",
                description="Simulate a hypothetical plan adjustment (reduced pacing, defer optional skills, deadline change) without modifying active mission.",
                parameters={
                    "type": "object",
                    "properties": {
                        "variant_type": {
                            "type": "string",
                            "enum": ["pacing_reduction", "defer_optional", "target_date_acceleration", "custom_hours", "reprioritize_incomplete"],
                            "description": "Simulation adjustment type",
                        },
                        "weekly_hours": {"type": "integer", "description": "Hypothetical weekly commitment (1-80 hours)"},
                        "target_date": {"type": "string", "description": "Hypothetical target completion date (YYYY-MM-DD)"},
                        "defer_optional_skills": {"type": "boolean", "description": "Whether to defer non-mandatory elective requirements"},
                        "temporary_availability_overrides": {"type": "object", "description": "Optional temporary availability overrides"},
                        "rationale": {"type": "string", "description": "Untrusted descriptive rationale"},
                    },
                    "required": ["variant_type"],
                },
                returns={"type": "object", "properties": {"simulation_id": {"type": "string"}, "validity_status": {"type": "string"}, "feasibility_assessment": {"type": "string"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="compare_plan_variants",
                description="Compare two or more simulation results across feasibility, effort, and trade-offs.",
                parameters={
                    "type": "object",
                    "properties": {
                        "simulations": {"type": "array", "items": {"type": "object"}, "description": "List of at least two simulation results to compare"}
                    },
                    "required": ["simulations"],
                },
                returns={"type": "object", "properties": {"total_variants_compared": {"type": "integer"}, "feasible_variants_count": {"type": "integer"}, "tradeoff_analysis": {"type": "array"}}},
                permission_tier="read_only",
            ),
            ToolDefinition(
                name="check_prerequisite_safety",
                description="Validate whether target skills and completed skills form a cycle-free DAG and identify missing prerequisites.",
                parameters={
                    "type": "object",
                    "properties": {
                        "target_skills": {"type": "array", "items": {"type": "integer"}, "description": "Skill IDs proposed to target"},
                        "completed_skills": {"type": "array", "items": {"type": "integer"}, "description": "Skill IDs already mastered"},
                    },
                    "required": ["target_skills"],
                },
                returns={"type": "object", "properties": {"is_safe": {"type": "boolean"}, "has_cycle": {"type": "boolean"}, "missing_prerequisites": {"type": "array"}}},
                permission_tier="read_only",
            ),
        ]

    def export_gemini_tools(self) -> list[dict[str, Any]]:
        """Export tool signatures formatted for the Google Gemini Tool Calling API."""
        from app.agent.providers import normalize_gemini_schema

        return [
            {
                "function_declarations": [
                    {
                        "name": td.name,
                        "description": td.description,
                        "parameters": normalize_gemini_schema(td.parameters),
                    }
                    for td in self.get_tool_definitions()
                ]
            }
        ]

    def export_openai_tools(self) -> list[dict[str, Any]]:
        """Export tool signatures formatted for the OpenAI Tool Calling API."""
        return [
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            }
            for td in self.get_tool_definitions()
        ]

