"""Comprehensive tests for Phase 3.4 Agentic AI Foundation.

Covers:
1. Valid and invalid event schema validation.
2. Duplicate event handling (idempotency).
3. Irrelevant events producing no mission changes (no_action).
4. Deadline moved earlier workflow producing proposed_mission_adjustment and pending proposal.
5. Deadline extended workflow producing informational_notification.
6. Missing/invalid deadline producing human_review_required.
7. Untrusted source requiring human review.
8. Mission already completed producing no_action.
9. Zero or negative weekly availability producing human_review_required.
10. Completed task preservation across proposed plan revision and approval.
11. Deterministic rule-based fallback when LLM is unavailable.
12. Mock LLM provider execution with structured tradeoffs.
13. Malformed LLM output fallback recovery.
14. Tool permission enforcement (rejecting forbidden tools and cross-student access).
15. Tool-call iteration tracking.
16. Proposal remaining in pending status (NEVER auto-approved).
17. Audit log persistence in agent_runs with sanitized tool I/O.
18. Demo simulation endpoints and honest simulation labeling.
"""
import pytest
from datetime import datetime, timedelta
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
)
from app.agent.tools import AgentToolRegistry, ToolPermissionError
from app.agent.evaluator import calculate_deadline_metrics
from app.agent.llm import LLMAdapter
from app.agent.service import AgentService
from app.schemas import AgentEventCreateRequest, AgentSimulateRequest

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_agentic_state():
    """Ensure clean mission, proposal, and agent state before each test."""
    with SessionLocal() as db:
        db.query(AgentRun).delete()
        db.query(AgentEvent).delete()
        db.query(TaskProgressEvent).delete()
        db.query(MissionTask).delete()
        db.query(MissionChangeProposal).delete()
        db.query(MissionVersion).delete()
        db.query(CareerMission).delete()
        db.commit()
    yield


def _setup_active_mission(weekly_hours: int = 15) -> int:
    """Helper to create an active Career Mission for the dev student."""
    resp = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": weekly_hours,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_valid_and_invalid_event_ingest():
    """1. Ingesting valid event succeeds (201); invalid schema is rejected (422)."""
    _setup_active_mission()

    # Valid event
    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "previous_value": (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d"),
            "new_value": (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
            "source_reliability": "verified_employer",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] in ("proposed_mission_adjustment", "human_review_required")
    assert data["engine_used"] == "deterministic_rules"
    assert "tools_invoked" in data
    assert len(data["tools_invoked"]) >= 3

    # Invalid event_type
    bad_res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "invalid_event_type_xyz",
            "source": "some_source",
        },
    )
    assert bad_res.status_code == 422


def test_duplicate_event_handling():
    """2. Repeated event with identical event_id is handled idempotently."""
    _setup_active_mission()

    payload = {
        "event_id": "evt_fixed_duplicate_001",
        "event_type": "internship_deadline_changed",
        "source": "employer_portal",
        "role_id": "distributed-systems-intern",
        "new_value": (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d"),
    }

    res1 = client.post("/v1/agent/events", json=payload)
    assert res1.status_code == 201
    run1_id = res1.json()["id"]

    # Duplicate call
    res2 = client.post("/v1/agent/events", json=payload)
    assert res2.status_code == 201
    run2_id = res2.json()["id"]

    assert run1_id == run2_id  # Returned existing run without duplicating

    with SessionLocal() as db:
        events_count = db.query(AgentEvent).filter(AgentEvent.event_id == "evt_fixed_duplicate_001").count()
        assert events_count == 1


def test_irrelevant_event_handling():
    """3. Event for an unrelated internship role produces no_action and creates no proposal."""
    _setup_active_mission()  # active on distributed-systems-intern

    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "backend-api-intern",  # different role!
            "new_value": (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d"),
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] == "no_action"
    assert "not relevant" in data["decision_explanation"].lower()
    assert data["proposal_id"] is None

    # Check event status in DB is ignored
    with SessionLocal() as db:
        ev = db.query(AgentEvent).filter(AgentEvent.event_id == data["event_id"]).first()
        assert ev.processing_status == "ignored"


def test_deadline_moved_earlier_workflow():
    """4. Deadline moved earlier triggers proposed_mission_adjustment and stages pending proposal."""
    mission_id = _setup_active_mission(weekly_hours=15)

    now = datetime.utcnow()
    new_dl = (now + timedelta(days=50)).strftime("%Y-%m-%d")
    prev_dl = (now + timedelta(days=120)).strftime("%Y-%m-%d")

    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "previous_value": prev_dl,
            "new_value": new_dl,
            "source_reliability": "verified_employer",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] == "proposed_mission_adjustment"
    assert data["proposal_id"] is not None

    # Verify proposal in database is strictly 'pending' and base_version_number is 1
    with SessionLocal() as db:
        prop = db.query(MissionChangeProposal).filter(MissionChangeProposal.id == data["proposal_id"]).first()
        assert prop is not None
        assert prop.status == "pending"
        assert prop.mission_id == mission_id
        assert prop.base_version_number == 1
        assert "Pacing Adjustment" in prop.proposal_title

        # Verify active mission version was NOT mutated (still version 1 and active)
        active_v = db.query(MissionVersion).filter(MissionVersion.mission_id == mission_id, MissionVersion.is_active == True).first()
        assert active_v.version_number == 1


def test_deadline_extended_workflow():
    """5. Deadline extended significantly triggers informational_notification without proposal."""
    _setup_active_mission(weekly_hours=15)

    now = datetime.utcnow()
    prev_dl = (now + timedelta(days=20)).strftime("%Y-%m-%d")
    new_dl = (now + timedelta(days=90)).strftime("%Y-%m-%d")

    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "previous_value": prev_dl,
            "new_value": new_dl,
            "source_reliability": "verified_employer",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] == "informational_notification"
    assert data["proposal_id"] is None
    assert "extended" in data["decision_explanation"].lower()


def test_missing_or_invalid_deadline():
    """6. Missing or invalid date triggers human_review_required."""
    _setup_active_mission()

    # Missing date
    res1 = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "new_value": None,
        },
    )
    assert res1.status_code == 201
    assert res1.json()["decision_category"] == "human_review_required"

    # Malformed date string
    res2 = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "new_value": "not-a-valid-date-string",
        },
    )
    assert res2.status_code == 201
    assert res2.json()["decision_category"] == "human_review_required"


def test_untrusted_source_reliability():
    """7. Event from unverified third-party triggers human_review_required."""
    _setup_active_mission()

    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "unverified_forum",
            "role_id": "distributed-systems-intern",
            "new_value": (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d"),
            "source_reliability": "unverified_third_party",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] == "human_review_required"
    assert "unverified third-party" in data["decision_explanation"].lower()


def test_mission_already_completed():
    """8. When all tasks in mission are completed, deadline change produces no_action."""
    mission_id = _setup_active_mission()

    # Mark all tasks in active mission as completed
    with SessionLocal() as db:
        tasks = (
            db.query(MissionTask)
            .join(MissionVersion)
            .filter(MissionVersion.mission_id == mission_id)
            .all()
        )
        for t in tasks:
            t.status = "completed"
            t.completed_at = datetime.utcnow()
        db.commit()

    res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "new_value": (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d"),
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["decision_category"] == "no_action"
    assert "already achieved 100% completion" in data["decision_explanation"].lower()


def test_zero_weekly_hours_capacity():
    """9. Evaluator handles zero weekly hours with human_review_required."""
    res = calculate_deadline_metrics(
        current_deadline="2026-12-01",
        new_deadline="2026-11-01",
        weekly_hours=0,
        remaining_tasks=[{"estimated_hours_min": 10, "estimated_hours_max": 20}],
    )
    assert res["decision_category"] == "human_review_required"
    assert "weekly preparation availability" in res["explanation"].lower()


def test_completed_task_preservation():
    """10. Completing a task, staging an agent revision, and human-approving preserves completed work."""
    mission_id = _setup_active_mission(weekly_hours=15)

    # 1. Complete task 1
    with SessionLocal() as db:
        first_task = (
            db.query(MissionTask)
            .join(MissionVersion)
            .filter(MissionVersion.mission_id == mission_id)
            .order_by(MissionTask.id.asc())
            .first()
        )
        first_task_id = first_task.id
        first_task_key = first_task.stable_key

    task_update_res = client.patch(
        f"/v1/missions/{mission_id}/tasks/{first_task_id}/status",
        json={"status": "completed", "override_reason": "Completed prerequisite coursework"},
    )
    assert task_update_res.status_code == 200


    # 2. Ingest deadline earlier event
    agent_res = client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "previous_value": (datetime.utcnow() + timedelta(days=120)).strftime("%Y-%m-%d"),
            "new_value": (datetime.utcnow() + timedelta(days=50)).strftime("%Y-%m-%d"),
        },

    )
    assert agent_res.status_code == 201
    proposal_id = agent_res.json()["proposal_id"]
    assert proposal_id is not None

    # 3. Human explicitly approves the proposal
    approval_res = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/approve",
        json={"decision_notes": "Approved revised pace."},
    )
    assert approval_res.status_code == 200

    # 4. Verify Version 2.0 is active and first_task is still completed!
    mission_res = client.get(f"/v1/missions/{mission_id}")
    assert mission_res.status_code == 200
    m_data = mission_res.json()
    assert m_data["active_version_number"] == 2

    active_tasks = m_data["active_version"]["tasks"]
    matching_task = next((t for t in active_tasks if t["stable_key"] == first_task_key), None)
    assert matching_task is not None
    assert matching_task["status"] == "completed"


def test_llm_unavailable_deterministic_fallback():
    """11. LLM adapter falls back to deterministic rules when no keys are present."""
    adapter = LLMAdapter(provider="deterministic")
    assert not adapter.is_llm_available()
    assert adapter.get_engine_label() == "deterministic_rules"

    decision, engine, _ = adapter.synthesize_decision(
        event_summary={"new_value": "2026-11-15"},
        deterministic_result={
            "decision_category": "proposed_mission_adjustment",
            "explanation": "Pacing calculation requires proposal.",
        },
        student_context={"name": "Alex Chen", "email": "alex@secret.com"},
        mission_summary={"title": "Career Mission"},
    )
    assert decision.decision_category == "proposed_mission_adjustment"
    assert engine == "deterministic_rules"


def test_mock_llm_integration():
    """12. Mock LLM provider returns LLM reasoning format with tradeoffs."""
    adapter = LLMAdapter(provider="mock")
    assert adapter.is_llm_available()
    assert adapter.get_engine_label() == "mock_llm"

    decision, engine, telemetry = adapter.synthesize_decision(
        event_summary={"new_value": "2026-11-15"},
        deterministic_result={
            "decision_category": "proposed_mission_adjustment",
            "explanation": "Pacing calculation requires adjustment.",
        },
        student_context={"name": "Alex Chen"},
        mission_summary={"title": "Career Mission"},
    )
    assert engine == "mock_llm"
    assert "[Mock LLM Analysis]" in decision.explanation
    assert len(decision.tradeoffs) >= 2


def test_malformed_llm_output_fallback():
    """13. Real LLM failures or malformed outputs fall back gracefully to deterministic rules."""
    adapter = LLMAdapter(provider="gemini", model="gemini-1.5-flash")
    adapter.gemini_key = "fake_invalid_key"

    decision, engine, telemetry = adapter.synthesize_decision(
        event_summary={"new_value": "2026-11-15"},
        deterministic_result={
            "decision_category": "informational_notification",
            "explanation": "Deadline on track.",
        },
        student_context={"name": "Alex Chen"},
        mission_summary={},
    )
    # Failed API call triggers clean fallback to deterministic rules
    assert engine == "deterministic_rules"
    assert decision.decision_category == "informational_notification"
    assert telemetry.get("fallback") is True


def test_tool_permission_enforcement():
    """14. Backend tool registry enforces tenant isolation and rejects forbidden actions."""
    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Forbidden actions rejected
        forbidden_tools = [
            "approve_proposal",
            "modify_mission_version",
            "delete_evidence",
            "change_verified_skill",
            "submit_application",
        ]
        for tool in forbidden_tools:
            with pytest.raises(ToolPermissionError) as exc_info:
                registry.execute_tool(tool)
            assert "Forbidden" in str(exc_info.value)

        # Cross-student boundary violation rejected
        with pytest.raises(ToolPermissionError) as exc_info:
            registry.execute_tool("read_student_profile", student_id=student.id + 999)
        assert "Security violation" in str(exc_info.value) or "forbidden" in str(exc_info.value).lower()


def test_tool_iteration_limits_and_audit():
    """15. Tool executions are recorded with sanitized inputs and outputs."""
    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        registry.execute_tool("read_student_profile", student_id=student.id)
        assert len(registry.invocations) == 1
        rec = registry.invocations[0]
        assert rec.tool_name == "read_student_profile"
        assert "password" not in rec.sanitized_output
        assert "email" not in rec.sanitized_input


def test_audit_log_persistence():
    """16. Verify audit logs can be queried via API."""
    _setup_active_mission()

    client.post(
        "/v1/agent/events",
        json={
            "event_type": "internship_deadline_changed",
            "source": "employer_portal",
            "role_id": "distributed-systems-intern",
            "new_value": (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d"),
        },
    )

    runs_res = client.get("/v1/agent/runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1

    first_run = runs[0]
    detail_res = client.get(f"/v1/agent/runs/{first_run['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == first_run["id"]
    assert len(detail["tools_invoked"]) >= 1
    assert len(detail["tool_io_log"]) >= 1


def test_demo_simulation_endpoints():
    """17. Verify demo simulation scenarios and truthful demo labeling."""
    _setup_active_mission()

    scenarios = [
        ("deadline_earlier", "proposed_mission_adjustment"),
        ("deadline_extended", "informational_notification"),
        ("unrelated_role", "no_action"),
        ("evidence_added", "informational_notification"),
        ("untrusted_source", "human_review_required"),
    ]

    for scenario, expected_decision in scenarios:
        sim_res = client.post(
            "/v1/agent/events/simulate",
            json={"scenario": scenario},
        )
        assert sim_res.status_code == 201
        data = sim_res.json()
        assert data["is_simulated"] is True
        assert data["decision_category"] == expected_decision

    # Events list shows simulated events labeled
    events_res = client.get("/v1/agent/events")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= len(scenarios)
    for ev in events:
        if ev["source"] in ("simulated_demo_portal", "simulated_demo", "unverified_forum_post"):
            assert ev["is_simulated"] is True
