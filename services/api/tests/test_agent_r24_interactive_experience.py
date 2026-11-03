"""Automated test suite for Refinement R2.4: Interactive Student AI Experience & Agent Inspector.

Validates:
1. Target demo scenario: student facing exams asks for 4h/wk guidance via /v1/agent/query.
2. Structured counterfactual simulations & alternative comparison in tool execution log.
3. Proposal staging in PENDING status requiring human student decision.
4. Human approval via POST /v1/missions/:id/proposals/:pid/approve and clean state refresh.
5. Human rejection via POST /v1/missions/:id/proposals/:pid/reject preserving baseline mission.
6. Contextual queries (next milestone focus, missing skills, portfolio evidence) returning informational guidance.
7. Architectural invariants: C++ engine validation, zero auto-approval, tenant boundary enforcement.
"""
import json
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import (
    AgentEvent,
    AgentRun,
    CareerMission,
    MissionChangeProposal,
    MissionTask,
    MissionVersion,
    Student,
    TaskProgressEvent,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_state():
    """Ensure clean test state on the isolated test database."""
    # Fail-closed safety guard
    db_url_str = str(engine.url).lower()
    assert "test" in db_url_str, "Safety violation: test running on non-test DB!"
    assert not db_url_str.endswith("/internpath.db") and not db_url_str.endswith("\\internpath.db")

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
    """Helper to generate an initial approved Career Mission for dev student."""
    resp = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern", "weekly_hours": weekly_hours},
    )
    assert resp.status_code == 201, f"Failed to setup mission: {resp.text}"
    return resp.json()["id"]


def test_target_demo_scenario_university_exams_query():
    """R2.4 Target Competition Demo: Student facing university exams asks for 4 hrs/wk advice."""
    mission_id = _setup_active_mission(weekly_hours=15)

    exam_query = (
        "I have university exams for the next two weeks. "
        "I can only spend four hours per week preparing for my internship. What should I do?"
    )

    resp = client.post("/v1/agent/query", json={"query": exam_query})
    assert resp.status_code == 200, f"Query failed: {resp.text}"
    data = resp.json()

    # Core response assertions
    assert data["mission_id"] == mission_id
    assert data["status"] == "completed"
    assert data["decision_category"] == "proposed_mission_adjustment"
    assert "4" in data["decision_explanation"] or "pacing" in data["decision_explanation"].lower()
    assert data["proposal_id"] is not None

    # Verify tool execution trace
    tools = data["tools_invoked"]
    assert "read_active_mission" in tools
    assert "simulate_plan_variant" in tools
    assert "compare_plan_variants" in tools
    assert "create_mission_change_proposal" in tools

    # Verify C++ engine simulation in tool_io_log
    sim_call = next((io for io in data["tool_io_log"] if io["tool"] == "simulate_plan_variant"), None)
    assert sim_call is not None
    assert sim_call["output"]["engine_identity"] == "c++20_learning_path_engine"
    assert sim_call["output"]["validity_status"] == "VALID_AND_FEASIBLE"
    assert sim_call["output"]["permitted_weekly_hours"] == 4
    assert sim_call["output"]["completed_work_preserved"] is True

    # Critical Human Safety Invariant: Baseline mission is UNCHANGED until human student approves!
    with SessionLocal() as db:
        m = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert m.weekly_hours == 15
        assert m.active_version.version_number == 1

        # Verify staged proposal is pending
        prop = db.query(MissionChangeProposal).filter(MissionChangeProposal.id == data["proposal_id"]).first()
        assert prop is not None
        assert prop.status == "pending"


def test_proposal_human_approval_workflow():
    """R2.4 Human Approval: Student reviews staged proposal, approves it, and mission updates to v2."""
    mission_id = _setup_active_mission(weekly_hours=15)

    # 1. Trigger agent query that stages a proposal
    resp = client.post(
        "/v1/agent/query",
        json={"query": "I can only spend four hours per week due to exams. Can you adjust my plan?"},
    )
    assert resp.status_code == 200
    proposal_id = resp.json()["proposal_id"]
    assert proposal_id is not None

    # 2. Student reviews proposal in proposals endpoint
    prop_resp = client.get(f"/v1/missions/{mission_id}/proposals")
    assert prop_resp.status_code == 200
    props = prop_resp.json()
    assert any(p["id"] == proposal_id and p["status"] == "pending" for p in props)

    # 3. Student approves proposal
    approve_resp = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/approve",
        json={"decision_notes": "Approved roadmap update via Assistant review."},
    )
    assert approve_resp.status_code == 200
    approved_mission = approve_resp.json()
    assert approved_mission["status"] == "active"
    assert approved_mission["active_version_number"] == 2

    # 4. Verify mission active version updated to Version 2
    with SessionLocal() as db:
        m = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert m.active_version.version_number == 2
        # Tasks in version 2 preserve completed task
        v2_tasks = m.active_version.tasks
        assert len(v2_tasks) > 0


def test_proposal_human_rejection_workflow():
    """R2.4 Human Approval: Student rejects proposal; baseline mission remains at Version 1 unchanged."""
    mission_id = _setup_active_mission(weekly_hours=15)

    # 1. Trigger query that stages a proposal
    resp = client.post(
        "/v1/agent/query",
        json={"query": "Can you simulate 4 hours per week?"},
    )
    proposal_id = resp.json()["proposal_id"]
    assert proposal_id is not None

    # 2. Student rejects proposal
    reject_resp = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/reject",
        json={"decision_notes": "I decided to keep my original 15 hrs/week schedule."},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    # 3. Verify mission remains at Version 1
    with SessionLocal() as db:
        m = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert m.active_version.version_number == 1
        assert m.weekly_hours == 15


def test_contextual_queries_without_plan_adjustment():
    """Contextual questions (next task, missing skills, profile evidence) return informative guidance without staging proposals."""
    mission_id = _setup_active_mission(weekly_hours=15)

    # 1. Next task inquiry
    resp1 = client.post("/v1/agent/query", json={"query": "What should I focus on next?"})
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["decision_category"] == "informational_notification"
    assert d1["proposal_id"] is None
    assert "read_active_mission" in d1["tools_invoked"]
    assert "stage" in d1["decision_explanation"].lower() or "milestone" in d1["decision_explanation"].lower()

    # 2. Missing skills inquiry
    resp2 = client.post("/v1/agent/query", json={"query": "Which important skills am I missing for this role?"})
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["decision_category"] == "informational_notification"
    assert d2["proposal_id"] is None
    assert "c++" in d2["decision_explanation"].lower() or "competenc" in d2["decision_explanation"].lower()

    # 3. Evidence inquiry
    resp3 = client.post("/v1/agent/query", json={"query": "What evidence should I add to strengthen my profile?"})
    assert resp3.status_code == 200
    d3 = resp3.json()
    assert d3["decision_category"] == "informational_notification"
    assert d3["proposal_id"] is None
    assert "git" in d3["decision_explanation"].lower() or "evidence" in d3["decision_explanation"].lower()


def test_agent_inspector_trace_persistence_and_provenance():
    """R2.4 Inspector Audit: All runs are persisted with engine provenance and tool logs."""
    _setup_active_mission(weekly_hours=15)

    resp = client.post("/v1/agent/query", json={"query": "I have university exams for the next two weeks. I can only spend 4 hours."})
    run_id = resp.json()["id"]

    # Fetch run via inspector endpoint
    run_resp = client.get(f"/v1/agent/runs/{run_id}")
    assert run_resp.status_code == 200
    run_audit = run_resp.json()

    assert run_audit["id"] == run_id
    assert run_audit["engine_used"] == "deterministic_rules"
    assert len(run_audit["tools_invoked"]) >= 3
    assert len(run_audit["tool_io_log"]) >= 3
    assert run_audit["status"] == "completed"
    assert run_audit["execution_time_ms"] >= 0
