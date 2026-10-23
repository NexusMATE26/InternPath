"""Authorized tool registry for InternPath Agentic AI.

Enforces backend permission boundaries:
- Read-only queries for active student scope
- Pure computational engines (C++ graph solver, deadline calculator, diff analyzer)
- Staged write tool: creating a pending mission change proposal (NEVER auto-approving)
- Rejection of unauthorized actions (e.g., self-approval, direct mission mutation,
  cross-student access, application submission, skill level modification).
"""
import json
from typing import Any, Callable, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app import crud, models
from app.agent.clock import get_utc_now, parse_datetime_safe
from app.agent.evaluator import calculate_deadline_metrics
from app.bridge import run_learning_path_with_graph


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
        "modify_mission_version": "Mission versions are immutable snapshots. Cannot modify directly.",
        "delete_evidence": "Agent cannot delete student portfolio evidence.",
        "change_verified_skill": "Agent cannot alter verified skill levels.",
        "submit_application": "Agent cannot submit job applications autonomously.",
        "bypass_human_consent": "Agent cannot activate revised roadmaps without explicit student consent.",
    }

    def __init__(self, db: Session, context_student_id: int):
        self.db = db
        self.context_student_id = context_student_id
        self.invocations: list[ToolExecutionRecord] = []
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
        }

    def get_registered_tool_names(self) -> list[str]:
        return list(self._registry.keys())

    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool with strict permission checking and audit logging."""
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
        if "student_id" in kwargs and kwargs["student_id"] != self.context_student_id:
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
        except ToolPermissionError:
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
        proposed_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Stage a pending mission change proposal.

        CRITICAL SAFETY BOUNDARY:
        This tool creates a proposal in 'pending' status for human student review.
        It NEVER automatically approves the proposal or mutates the active mission version.
        """
        proposal = crud.create_mission_change_proposal(
            db=self.db,
            mission_id=mission_id,
            student_id=self.context_student_id,
            proposal_title=proposal_title,
            rationale=rationale,
            proposed_plan=proposed_plan,
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
