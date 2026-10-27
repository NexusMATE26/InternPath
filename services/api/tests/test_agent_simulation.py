"""Comprehensive tests for Refinement R2.1: Secure Agent Tool Contracts & Counterfactual Plan Simulation.

Covers:
1. Valid simulated variants (pacing reduction, custom hours, defer optional skills).
2. Temporary availability overrides.
3. Feasible target date evaluation (VALID_AND_FEASIBLE).
4. Infeasible deadline evaluation (VALID_BUT_INFEASIBLE).
5. Invalid weekly hours rejection (bounds: 1 to 80).
6. Invalid and past date rejection.
7. Unknown variant type rejection.
8. Missing active mission handling.
9. Cross-student tenant boundary security isolation.
10. Completed task preservation across simulations.
11. Zero database side effects / snapshot preservation (database strictly immutable during simulation).
12. Alternative comparison (compare_plan_variants) with feasible & infeasible tradeoffs.
13. Alternative comparison requiring at least two variants.
14. Prerequisite safety check (check_prerequisite_safety) for valid DAG.
15. Prerequisite safety check rejecting unknown skill IDs.
16. Mandatory requirement preservation (cannot silently drop mandatory skills).
17. Forbidden tool invocations (approve_proposal, activate_mission, modify_verified_skill, arbitrary shell/SQL).
18. Tool definitions catalog and provider exports (Gemini and OpenAI schemas).
19. Input payload size bound enforcement (16KB limit).
20. Deterministic simulation consistency (identical inputs produce identical calculations).
21. Live HTTP endpoints for simulation, comparison, safety check, and tool export.
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import (
    Student,
    CareerMission,
    MissionVersion,
    MissionTask,
    TaskProgressEvent,
    MissionChangeProposal,
    AgentEvent,
    AgentRun,
    StudentSkill,
    EvidenceItem,
)
from app.agent.tools import AgentToolRegistry, ToolPermissionError
from app.schemas import (
    PlanVariantType,
    ValidityStatus,
    SimulatePlanVariantRequest,
    ComparePlanVariantsRequest,
    CheckPrerequisiteSafetyRequest,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_simulation_state():
    """Ensure clean mission and agent state before each test."""
    with SessionLocal() as db:
        db.query(AgentRun).delete()
        db.query(AgentEvent).delete()
        db.query(TaskProgressEvent).delete()
        db.query(MissionTask).delete()
        db.query(MissionChangeProposal).delete()
        db.query(MissionVersion).delete()
        db.query(CareerMission).delete()
        db.query(EvidenceItem).delete()
        db.commit()
    yield


def _setup_active_mission(weekly_hours: int = 15, role_id: str = "distributed-systems-intern") -> int:
    """Helper to create an active Career Mission."""
    resp = client.post(
        "/v1/missions",
        json={
            "target_role_id": role_id,
            "weekly_hours": weekly_hours,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. Valid Simulation Variants
# ---------------------------------------------------------------------------

def test_simulate_plan_variant_valid_pacing_reduction():
    """Simulate a pacing reduction variant with lower weekly hours."""
    mission_id = _setup_active_mission(weekly_hours=20)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="pacing_reduction",
            weekly_hours=10,
            mission_id=mission_id,
        )

        assert res["mission_id"] == mission_id
        assert res["variant_type"] == "pacing_reduction"
        assert res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value
        assert res["permitted_weekly_hours"] == 10
        assert res["estimated_remaining_hours_min"] > 0
        assert res["estimated_remaining_hours_max"] >= res["estimated_remaining_hours_min"]
        assert res["estimated_weeks_range"][0] > 0
        assert res["engine_identity"] == "c++20_learning_path_engine"
        assert res["completed_work_preserved"] is True
        assert res["mandatory_requirements_preserved"] is True
        assert "simulation_id" in res
        assert res["trace_reference"] is not None


def test_simulate_plan_variant_defer_optional_skills():
    """Simulate deferring optional/elective role requirements."""
    mission_id = _setup_active_mission(weekly_hours=15, role_id="distributed-systems-intern")

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # 1. Base simulation without deferring
        full_res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="custom_hours",
            weekly_hours=15,
            defer_optional_skills=False,
        )

        # 2. Variant deferring optional skills
        defer_res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="defer_optional",
            weekly_hours=15,
            defer_optional_skills=True,
        )

        assert defer_res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value
        assert defer_res["mandatory_requirements_preserved"] is True
        # If the role has non-structural electives, remaining hours should be <= full plan
        assert defer_res["estimated_remaining_hours_max"] <= full_res["estimated_remaining_hours_max"]
        assert "tasks_summary" in defer_res


def test_simulate_plan_variant_temporary_availability_overrides():
    """Simulate temporary reduced availability during exam or crunch periods."""
    mission_id = _setup_active_mission(weekly_hours=20)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="pacing_reduction",
            temporary_availability_overrides={"override_hours": 6, "weeks": 4},
        )

        assert res["permitted_weekly_hours"] == 6
        assert "temporary override" in res["feasibility_assessment"]
        assert res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value


# ---------------------------------------------------------------------------
# 2. Deadline Feasibility: FEASIBLE vs INFEASIBLE
# ---------------------------------------------------------------------------

def test_simulate_plan_variant_feasible_target_date():
    """Target date far enough in future evaluates to VALID_AND_FEASIBLE."""
    _setup_active_mission(weekly_hours=15)
    future_date = (datetime.now(timezone.utc) + timedelta(days=200)).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="target_date_acceleration",
            target_date=future_date,
            weekly_hours=15,
        )

        assert res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value
        assert "Feasible" in res["feasibility_assessment"]
        assert len(res["feasibility_limitations"]) == 0


def test_simulate_plan_variant_infeasible_deadline():
    """Very tight target date evaluates to VALID_BUT_INFEASIBLE."""
    _setup_active_mission(weekly_hours=10)
    tight_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="target_date_acceleration",
            target_date=tight_date,
            weekly_hours=10,
        )

        assert res["validity_status"] == ValidityStatus.VALID_BUT_INFEASIBLE.value
        assert "Infeasible against target date" in res["feasibility_assessment"]
        assert len(res["feasibility_limitations"]) > 0


# ---------------------------------------------------------------------------
# 3. Input Validation and Security Boundaries
# ---------------------------------------------------------------------------

def test_simulate_plan_variant_invalid_weekly_hours():
    """Weekly hours <= 0 or > 80 are strictly rejected."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="weekly_hours must be an integer between 1 and 80"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=0)

        with pytest.raises(ValueError, match="weekly_hours must be an integer between 1 and 80"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=-10)

        with pytest.raises(ValueError, match="weekly_hours must be an integer between 1 and 80"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=99)


def test_simulate_plan_variant_invalid_target_dates():
    """Past target dates or malformed strings are strictly rejected."""
    _setup_active_mission()
    past_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="is in the past"):
            registry.execute_tool("simulate_plan_variant", variant_type="target_date_acceleration", target_date=past_date)

        with pytest.raises(ValueError, match="Invalid target_date format"):
            registry.execute_tool("simulate_plan_variant", variant_type="target_date_acceleration", target_date="not-a-valid-date")


def test_simulate_plan_variant_unknown_variant_type():
    """Unknown variant types outside PlanVariantType enum are rejected."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="Unknown variant type"):
            registry.execute_tool("simulate_plan_variant", variant_type="warp_speed_skip_everything")


def test_simulate_plan_variant_missing_mission():
    """Attempting simulation without an active Career Mission raises clear error."""
    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="does not have an active career mission"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction")


def test_cross_student_tenant_boundary_isolation():
    """Attempting to access or simulate for another student ID raises ToolPermissionError."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Explicit cross-student access attempt
        with pytest.raises(ToolPermissionError, match="Security violation"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", student_id=student.id + 999)


# ---------------------------------------------------------------------------
# 4. Completed Work Preservation and Zero DB Side Effects
# ---------------------------------------------------------------------------

def test_simulation_preserves_completed_work():
    """Completed tasks and evidence links remain intact and are recognized in simulation."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        mission = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert mission.active_version is not None
        first_task = mission.active_version.tasks[0]
        first_task.status = "completed"
        first_task.completed_at = datetime.now(timezone.utc)
        db.commit()

        student_id = mission.student_id
        task_id = first_task.id

    with SessionLocal() as db:
        registry = AgentToolRegistry(db, student_id)
        sim_res = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)

        assert sim_res["completed_work_preserved"] is True
        assert sim_res["tasks_summary"]["completed_preserved"] >= 1

        # Check DB to verify status was NOT altered
        task_in_db = db.query(MissionTask).filter(MissionTask.id == task_id).first()
        assert task_in_db.status == "completed"


def test_simulation_zero_database_side_effects():
    """A simulation must NEVER write or mutate database records (CareerMission, MissionVersion, MissionTask)."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        missions_before = db.query(CareerMission).count()
        versions_before = db.query(MissionVersion).count()
        tasks_before = db.query(MissionTask).count()
        proposals_before = db.query(MissionChangeProposal).count()
        student = db.query(Student).first()

        registry = AgentToolRegistry(db, student.id)

        # Run several simulations
        registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=8)
        registry.execute_tool("simulate_plan_variant", variant_type="defer_optional", defer_optional_skills=True)
        registry.execute_tool("simulate_plan_variant", variant_type="custom_hours", weekly_hours=20)

        # Assert database counts are strictly identical
        assert db.query(CareerMission).count() == missions_before
        assert db.query(MissionVersion).count() == versions_before
        assert db.query(MissionTask).count() == tasks_before
        assert db.query(MissionChangeProposal).count() == proposals_before


def test_simulation_preserves_portfolio_evidence():
    """Portfolio evidence attached to students and skills remains untouched during simulation."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        student_id = student.id
        evidence = EvidenceItem(
            student_id=student_id,
            skill_id=1,
            title="Embedded RTOS Project",
            description="STM32 FreeRTOS project with ADC and UART drivers",
            url="https://github.com/student/stm32-rtos",
            evidence_type="project",
            verified_by_staff=True,
        )
        db.add(evidence)
        db.commit()
        evidence_id = evidence.id

    with SessionLocal() as db:
        registry = AgentToolRegistry(db, student_id)
        # Execute counterfactual simulations
        registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=8)
        registry.execute_tool("simulate_plan_variant", variant_type="defer_optional", defer_optional_skills=True)

        # Verify evidence item is completely unaltered
        stored_ev = db.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
        assert stored_ev is not None
        assert stored_ev.title == "Embedded RTOS Project"
        assert stored_ev.verified_by_staff is True
        assert stored_ev.url == "https://github.com/student/stm32-rtos"


def test_simulation_missing_active_version():
    """Simulation on a mission lacking an approved active version raises ValueError."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        student_id = student.id
        # Remove all versions so active_version is None
        db.query(MissionTask).delete()
        db.query(MissionVersion).delete()
        db.commit()

    with SessionLocal() as db:
        registry = AgentToolRegistry(db, student_id)
        with pytest.raises(ValueError, match="has no approved active version"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", mission_id=mission_id)


def test_simulation_temporary_availability_invalid_weeks():
    """Invalid temporary override weeks (negative or >52) are rejected."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="override weeks must be an integer between 1 and 52"):
            registry.execute_tool(
                "simulate_plan_variant",
                variant_type="pacing_reduction",
                temporary_availability_overrides={"override_hours": 10, "weeks": 0},
            )

        with pytest.raises(ValueError, match="override weeks must be an integer between 1 and 52"):
            registry.execute_tool(
                "simulate_plan_variant",
                variant_type="pacing_reduction",
                temporary_availability_overrides={"override_hours": 10, "weeks": 100},
            )


def test_simulation_engine_unavailable_handled(monkeypatch):
    """If C++ engine raises EngineUnavailable, the simulation fails safely without side-effects."""
    from app.bridge import EngineUnavailable
    import app.agent.tools

    _setup_active_mission()

    def mock_fail(*args, **kwargs):
        raise EngineUnavailable("Simulated engine timeout or unavailability")

    monkeypatch.setattr(app.agent.tools, "run_learning_path_with_graph", mock_fail)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(EngineUnavailable, match="Simulated engine timeout"):
            registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)

        # Audit log captures the error cleanly
        last_rec = registry.invocations[-1]
        assert last_rec.tool_name == "simulate_plan_variant"
        assert last_rec.sanitized_output.get("error") == "EngineUnavailable"


# ---------------------------------------------------------------------------
# 5. Alternative Comparison Tool (compare_plan_variants)
# ---------------------------------------------------------------------------

def test_compare_plan_variants():
    """compare_plan_variants compares two or more simulation results and details trade-offs."""
    _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        sim_a = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=12)
        sim_b = registry.execute_tool("simulate_plan_variant", variant_type="defer_optional", defer_optional_skills=True, weekly_hours=15)

        comp = registry.execute_tool("compare_plan_variants", simulations=[sim_a, sim_b])

        assert comp["total_variants_compared"] == 2
        assert len(comp["tradeoff_analysis"]) == 2
        assert len(comp["recommended_candidates"]) >= 1
        assert "comparison_matrix" in comp
        assert "recommendation_rationale" in comp
        assert comp["comparison_matrix"]["variants"] == ["pacing_reduction", "defer_optional"]


def test_compare_plan_variants_requires_at_least_two():
    """compare_plan_variants rejects fewer than 2 simulation results."""
    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)

        with pytest.raises(ValueError, match="requires at least two simulation results"):
            registry.execute_tool("compare_plan_variants", simulations=[])

        with pytest.raises(ValueError, match="requires at least two simulation results"):
            registry.execute_tool("compare_plan_variants", simulations=[{"variant_type": "one_only"}])


def test_compare_plan_variants_incompatible_missions():
    """compare_plan_variants rejects simulations from different career missions."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        sim_a = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)
        # Create a simulation dict with a different mission_id
        sim_b = dict(sim_a)
        sim_b["mission_id"] = sim_a["mission_id"] + 100

        with pytest.raises(ValueError, match="Incompatible variants: cannot compare simulations across different missions"):
            registry.execute_tool("compare_plan_variants", simulations=[sim_a, sim_b])


def test_compare_plan_variants_incompatible_versions():
    """compare_plan_variants rejects simulations computed from different base versions."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        sim_a = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)
        sim_b = dict(sim_a)
        sim_b["base_version_number"] = sim_a["base_version_number"] + 1

        with pytest.raises(ValueError, match="Incompatible variants: cannot compare simulations across different base versions"):
            registry.execute_tool("compare_plan_variants", simulations=[sim_a, sim_b])


def test_compare_plan_variants_cross_student_rejection():
    """compare_plan_variants rejects comparing simulations from another student's mission."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        other_student_id = student.id + 999
        other_registry = AgentToolRegistry(db, other_student_id)

        sim_a = AgentToolRegistry(db, student.id).execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)
        sim_b = AgentToolRegistry(db, student.id).execute_tool("simulate_plan_variant", variant_type="custom_hours", weekly_hours=15)

        with pytest.raises(ToolPermissionError, match="Security violation"):
            other_registry.execute_tool("compare_plan_variants", simulations=[sim_a, sim_b])


def test_compare_plan_variants_stale_version_rejection():
    """compare_plan_variants rejects simulations if the active mission version has advanced."""
    mission_id = _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        sim_a = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)
        sim_b = registry.execute_tool("simulate_plan_variant", variant_type="custom_hours", weekly_hours=15)

        # Advance active mission version
        mission = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        for v in mission.versions:
            v.is_active = False
        new_version = MissionVersion(
            mission_id=mission.id,
            version_number=mission.versions[-1].version_number + 1,
            title="Advanced version after approval",
            rationale="Advanced version after approval",
            is_active=True,
        )
        db.add(new_version)
        db.commit()

        # Comparing simulations computed against version 1 must now be rejected as stale
        with pytest.raises(ValueError, match="Stale simulation detected"):
            registry.execute_tool("compare_plan_variants", simulations=[sim_a, sim_b])


# ---------------------------------------------------------------------------
# 6. Prerequisite Safety Check Tool (check_prerequisite_safety)
# ---------------------------------------------------------------------------

def test_check_prerequisite_safety_valid_dag():
    """check_prerequisite_safety computes transitive closure and missing prerequisites."""
    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Target Backend APIs (skill 4) with no completed skills
        res = registry.execute_tool(
            "check_prerequisite_safety",
            target_skills=[4],
            completed_skills=[],
        )

        assert res["is_safe"] is True
        assert res["has_cycle"] is False
        # Skill 4 depends on Skill 2 (Python) and Skill 9 (SQL), which depend on Skill 1
        assert len(res["prerequisite_closure"]) >= 2
        assert len(res["missing_prerequisites"]) >= 2


def test_check_prerequisite_safety_unknown_skill():
    """check_prerequisite_safety rejects non-existent skill IDs."""
    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ValueError, match="does not exist in skill catalog"):
            registry.execute_tool("check_prerequisite_safety", target_skills=[99999])


# ---------------------------------------------------------------------------
# 7. Forbidden Actions and Tool Schemas
# ---------------------------------------------------------------------------

def test_forbidden_actions_enforcement():
    """Forbidden autonomous actions are strictly blocked by tool registry."""
    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)

        forbidden_list = [
            "approve_proposal",
            "activate_mission",
            "modify_verified_skill",
            "change_verified_skill",
            "modify_mission_version",
            "delete_evidence",
            "submit_application",
            "bypass_human_consent",
            "execute_command",
            "execute_sql",
            "arbitrary_shell",
            "arbitrary_sql",
        ]

        for action in forbidden_list:
            with pytest.raises(ToolPermissionError, match="Forbidden tool"):
                registry.execute_tool(action)


def test_tool_definitions_and_provider_exports():
    """Tool definitions are complete, provider-neutral, and exportable to Gemini/OpenAI formats."""
    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)

        tool_defs = registry.get_tool_definitions()
        assert len(tool_defs) == 14

        # Verify only create_mission_change_proposal has proposal_stage permission tier
        write_tools = [t for t in tool_defs if t.permission_tier == "proposal_stage"]
        assert len(write_tools) == 1
        assert write_tools[0].name == "create_mission_change_proposal"

        # Export for Gemini
        gemini_export = registry.export_gemini_tools()
        assert len(gemini_export) == 1
        assert "function_declarations" in gemini_export[0]
        assert len(gemini_export[0]["function_declarations"]) == 14

        # Export for OpenAI
        openai_export = registry.export_openai_tools()
        assert len(openai_export) == 14
        assert openai_export[0]["type"] == "function"
        assert "function" in openai_export[0]


def test_simulation_payload_size_limit():
    """Inputs exceeding 16KB are rejected by execute_tool bounds."""
    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)

        oversized_rationale = "x" * 20000
        with pytest.raises(ValueError, match="Input size limit exceeded"):
            registry.execute_tool(
                "simulate_plan_variant",
                variant_type="pacing_reduction",
                rationale=oversized_rationale,
            )


def test_simulation_determinism():
    """Identical simulation inputs yield strictly deterministic results."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res1 = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)
        res2 = registry.execute_tool("simulate_plan_variant", variant_type="pacing_reduction", weekly_hours=10)

        assert res1["estimated_remaining_hours_min"] == res2["estimated_remaining_hours_min"]
        assert res1["estimated_remaining_hours_max"] == res2["estimated_remaining_hours_max"]
        assert res1["estimated_weeks_range"] == res2["estimated_weeks_range"]
        assert res1["validity_status"] == res2["validity_status"]
        assert res1["tasks_summary"] == res2["tasks_summary"]


# ---------------------------------------------------------------------------
# 8. Live FastAPI HTTP Endpoint Testing
# ---------------------------------------------------------------------------

def test_api_simulate_plan_variant_endpoint():
    """POST /v1/agent/tools/simulate-plan-variant returns 200 and structured response."""
    _setup_active_mission(weekly_hours=15)

    resp = client.post(
        "/v1/agent/tools/simulate-plan-variant",
        json={
            "variant_type": "pacing_reduction",
            "weekly_hours": 12,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["validity_status"] == "VALID_AND_FEASIBLE"
    assert data["permitted_weekly_hours"] == 12
    assert "simulation_id" in data


def test_api_compare_plan_variants_endpoint():
    """POST /v1/agent/tools/compare-plan-variants returns 200 with trade-off analysis."""
    _setup_active_mission(weekly_hours=15)

    # 1. Run two simulations via API
    sim1 = client.post(
        "/v1/agent/tools/simulate-plan-variant",
        json={"variant_type": "pacing_reduction", "weekly_hours": 10},
    ).json()

    sim2 = client.post(
        "/v1/agent/tools/simulate-plan-variant",
        json={"variant_type": "custom_hours", "weekly_hours": 18},
    ).json()

    # 2. Compare via API
    comp_resp = client.post(
        "/v1/agent/tools/compare-plan-variants",
        json={"simulations": [sim1, sim2]},
    )
    assert comp_resp.status_code == 200
    data = comp_resp.json()
    assert data["total_variants_compared"] == 2
    assert len(data["tradeoff_analysis"]) == 2


def test_api_check_prerequisite_safety_endpoint():
    """POST /v1/agent/tools/check-prerequisite-safety returns 200."""
    resp = client.post(
        "/v1/agent/tools/check-prerequisite-safety",
        json={"target_skills": [4, 6], "completed_skills": [1, 2]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "is_safe" in data
    assert "prerequisite_closure" in data


def test_api_tool_schema_export_endpoints():
    """GET /v1/agent/tools, /v1/agent/tools/gemini, /v1/agent/tools/openai all return 200."""
    res_tools = client.get("/v1/agent/tools")
    assert res_tools.status_code == 200
    assert len(res_tools.json()) == 14

    res_gemini = client.get("/v1/agent/tools/gemini")
    assert res_gemini.status_code == 200
    assert "function_declarations" in res_gemini.json()[0]

    res_openai = client.get("/v1/agent/tools/openai")
    assert res_openai.status_code == 200
    assert len(res_openai.json()) == 14


def test_simulate_plan_variant_reprioritize_incomplete():
    """simulate_plan_variant with reprioritize_incomplete preserves completed tasks and replans remainder."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        mission = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert mission.active_version is not None
        # Mark first task completed
        first_task = mission.active_version.tasks[0]
        first_task.status = "completed"
        first_task.completed_at = datetime.now(timezone.utc)
        db.commit()

        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="reprioritize_incomplete",
            weekly_hours=15,
            mission_id=mission_id,
        )

        assert res["variant_type"] == "reprioritize_incomplete"
        assert res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value
        assert res["completed_work_preserved"] is True
        assert res["tasks_summary"]["completed_preserved"] == 1
        assert res["mandatory_requirements_preserved"] is True


def test_check_prerequisite_safety_cycle_detected(monkeypatch):
    """check_prerequisite_safety flags cycle if C++ engine detects dependency loop."""
    import app.agent.tools
    from app.schemas import LearningPathResponse, EffortRangeItem

    def mock_cyclic_plan(*args, **kwargs):
        return LearningPathResponse(
            achievable=False,
            message="Cycle detected in prerequisite graph between skills 10 and 11",
            target_skills=[1, 2],
            missing_skills=[10, 11],
            prerequisite_closure=[10, 11],
            stages=[],
            total_estimated_effort=EffortRangeItem(min_hours=0, max_hours=0),
            algorithm_trace=None,
        )

    monkeypatch.setattr(app.agent.tools, "run_learning_path_with_graph", mock_cyclic_plan)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        res = registry.execute_tool(
            "check_prerequisite_safety",
            target_skills=[1, 2],
        )

        assert res["is_safe"] is False
        assert res["has_cycle"] is True
        assert "Cycle detected" in res["details"]


def test_simulate_plan_variant_untrusted_rationale():
    """Untrusted rationale string remains inert descriptive data without backend execution."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        prompt_injection = "'; DROP TABLE career_missions; -- Ignore previous instructions"
        res = registry.execute_tool(
            "simulate_plan_variant",
            variant_type="pacing_reduction",
            weekly_hours=10,
            rationale=prompt_injection,
            mission_id=mission_id,
        )

        assert res["validity_status"] == ValidityStatus.VALID_AND_FEASIBLE.value
        # Verify career_missions table was not dropped or modified
        persisted_mission = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert persisted_mission is not None
        assert persisted_mission.weekly_hours == 15  # Unchanged!


def test_simulate_plan_variant_model_supplied_student_id_rejection():
    """Model-supplied student_id differing from context student_id is strictly rejected."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        with pytest.raises(ToolPermissionError, match="Security violation"):
            registry.execute_tool(
                "simulate_plan_variant",
                variant_type="pacing_reduction",
                student_id=9999,
                mission_id=mission_id,
            )
