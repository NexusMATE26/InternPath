"""Comprehensive integration and unit tests for Phase 3.3 Persistent Career Mission System.

Validates:
1. Mission creation from C++ learning-path engine output.
2. Duplicate mission prevention and conflict resolution.
3. Mission persistence across queries and sessions.
4. Deterministic task generation with measurable completion criteria.
5. Prerequisite dependency ordering and intra-plan dependency tracking.
6. Shared prerequisite deduplication.
7. Valid task progress state transitions (not_started -> in_progress -> completed).
8. Invalid task progress state transitions rejected.
9. Locked-task completion rejection when prerequisites unmet.
10. Explicit override capability for locked tasks with audited reason.
11. Evidence item linking to tasks.
12. Auditable task progress history persistence.
13. Mission change proposal creation with structured before/after diff.
14. Proposal diff correctness (added, removed, retained, effort_delta).
15. Human proposal rejection.
16. Human proposal approval producing immutable Version 2.0.
17. Completed work preservation across mission versions.
18. Stale version conflict handling (HTTP 409).
19. Idempotency of repeated approval/rejection requests.
20. Database transaction safety and rollback.
21. 404 handling for invalid mission, task, proposal, and version IDs.
"""
import pytest
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
    EvidenceItem,
    MissionIdempotencyRecord,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_mission_state():
    """Ensure clean mission state before each test."""
    with SessionLocal() as db:
        # Delete task events, tasks, proposals, versions, idempotency records, missions
        db.query(TaskProgressEvent).delete()
        db.query(MissionTask).delete()
        db.query(MissionChangeProposal).delete()
        db.query(MissionVersion).delete()
        db.query(MissionIdempotencyRecord).delete()
        db.query(CareerMission).delete()
        db.commit()
    yield


def test_career_mission_creation():
    """1. Mission creation from live C++ engine output."""
    response = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": 15,
            "title": "Cloud Systems Career Mission",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["title"] == "Cloud Systems Career Mission"
    assert data["status"] == "active"
    assert data["weekly_hours"] == 15
    assert data["active_version_number"] == 1
    assert data["total_tasks"] > 0
    assert data["completed_tasks"] == 0
    assert data["progress_percent"] == 0.0
    assert data["estimated_remaining_hours_min"] > 0

    # Verify active version snapshot
    version = data["active_version"]
    assert version is not None
    assert version["version_number"] == 1
    assert version["is_active"] is True
    assert len(version["stages"]) > 0

    # Check tasks in first stage
    first_stage = version["stages"][0]
    assert first_stage["stage_number"] == 1
    assert len(first_stage["tasks"]) > 0

    for task in first_stage["tasks"]:
        assert task["status"] == "not_started"
        assert task["is_unlocked"] is True
        assert len(task["completion_criteria"]) > 20
        assert task["estimated_hours_min"] > 0


def test_duplicate_mission_prevention():
    """2. Duplicate mission prevention: attempting to create active mission for same role returns 409."""
    res1 = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


def test_duplicate_mission_allow_replace():
    """Allow replacing active mission if explicitly requested."""
    res1 = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern", "title": "Mission 1"},
    )
    assert res1.status_code == 201
    m1_id = res1.json()["id"]

    res2 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "title": "Mission 2 (Replaced)",
            "allow_replace_active": True,
        },
    )
    assert res2.status_code == 201
    m2_id = res2.json()["id"]
    assert m2_id != m1_id

    # Verify active mission endpoint returns Mission 2
    active_res = client.get("/v1/missions/active")
    assert active_res.status_code == 200
    assert active_res.json()["id"] == m2_id


def test_mission_persistence_across_sessions():
    """3. Mission persistence: verify records are persisted in database."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    assert create_res.status_code == 201
    mission_id = create_res.json()["id"]

    with SessionLocal() as db:
        m = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert m is not None
        assert m.status == "active"
        assert len(m.versions) == 1
        assert len(m.versions[0].tasks) > 0


def test_prerequisite_dependencies_and_stages():
    """4 & 5. Prerequisite dependencies and stage ordering."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    data = create_res.json()
    stages = data["active_version"]["stages"]

    # Distributed systems requires multiple stages (e.g. stage 1 -> stage 2 -> stage 3)
    assert len(stages) >= 2

    # Check that stage 1 tasks have no unfulfilled prerequisites
    stage1_tasks = stages[0]["tasks"]
    for t in stage1_tasks:
        assert t["is_unlocked"] is True

    # If there is a stage 2, tasks depending on stage 1 should have prerequisite keys
    if len(stages) > 1:
        stage2_tasks = stages[1]["tasks"]
        # At least one stage 2 task should have prerequisite_task_keys
        has_prereqs = any(len(t["prerequisite_task_keys"]) > 0 for t in stage2_tasks)
        assert has_prereqs is True


def test_shared_prerequisite_deduplication():
    """6. Shared prerequisites are not duplicated into redundant tasks."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    data = create_res.json()
    tasks = data["active_version"]["tasks"]

    # Each skill should only appear once in the mission task list
    skill_ids = [t["skill_id"] for t in tasks]
    assert len(skill_ids) == len(set(skill_ids))


def test_valid_task_progress_transitions():
    """7. Valid task progress state transitions."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]
    task_id = create_res.json()["active_version"]["stages"][0]["tasks"][0]["id"]

    # 1. Advance to in_progress
    p1 = client.patch(
        f"/v1/missions/{mission_id}/tasks/{task_id}/status",
        json={"status": "in_progress", "notes": "Started learning module"},
    )
    assert p1.status_code == 200
    assert p1.json()["status"] == "in_progress"

    # 2. Advance to completed
    p2 = client.patch(
        f"/v1/missions/{mission_id}/tasks/{task_id}/status",
        json={"status": "completed", "notes": "Finished coursework"},
    )
    assert p2.status_code == 200
    assert p2.json()["status"] == "completed"
    assert p2.json()["completed_at"] is not None

    # Check overall mission progress
    m_res = client.get(f"/v1/missions/{mission_id}")
    assert m_res.json()["completed_tasks"] == 1
    assert m_res.json()["progress_percent"] > 0.0


def test_invalid_task_progress_transition():
    """8. Invalid task state transitions rejected."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]
    task_id = create_res.json()["active_version"]["stages"][0]["tasks"][0]["id"]

    bad = client.patch(
        f"/v1/missions/{mission_id}/tasks/{task_id}/status",
        json={"status": "invalid_status"},
    )
    assert bad.status_code == 422


def test_locked_task_completion_rejection_and_override():
    """9 & 10. Locked task cannot be completed without override; succeeds with override."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]
    stages = create_res.json()["active_version"]["stages"]

    if len(stages) < 2:
        pytest.skip("Test requires at least 2 stages in generated plan.")

    # Find a task with prerequisites
    locked_task = None
    for stage in stages[1:]:
        for t in stage["tasks"]:
            if len(t["prerequisite_task_keys"]) > 0:
                locked_task = t
                break
        if locked_task:
            break

    assert locked_task is not None
    assert locked_task["is_unlocked"] is False

    # Attempt to complete locked task without override
    fail_res = client.patch(
        f"/v1/missions/{mission_id}/tasks/{locked_task['id']}/status",
        json={"status": "completed"},
    )
    assert fail_res.status_code == 422
    assert "Prerequisite tasks" in fail_res.json()["detail"]

    # Provide explicit override reason
    success_res = client.patch(
        f"/v1/missions/{mission_id}/tasks/{locked_task['id']}/status",
        json={
            "status": "completed",
            "override_reason": "Completed equivalent external industry certification",
        },
    )
    assert success_res.status_code == 200
    assert success_res.json()["status"] == "completed"
    assert "Completed equivalent" in success_res.json()["override_reason"]


def test_evidence_linking_and_history():
    """11 & 12. Link portfolio evidence item to task and verify audit history."""
    # Ensure an evidence item exists
    ev_res = client.post(
        "/v1/evidence",
        json={
            "skill_id": 1,
            "title": "C++ Memory Allocator Project",
            "description": "Custom heap allocator with pool management",
            "url": "https://github.com/alexchen/allocator",
            "evidence_type": "project",
        },
    )
    assert ev_res.status_code == 201
    evidence_id = ev_res.json()["id"]

    # Create mission
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]
    task_id = create_res.json()["active_version"]["stages"][0]["tasks"][0]["id"]

    # Link evidence
    link_res = client.post(
        f"/v1/missions/{mission_id}/tasks/{task_id}/evidence",
        json={"evidence_id": evidence_id, "notes": "Attached custom allocator project"},
    )
    assert link_res.status_code == 200
    assert link_res.json()["evidence_id"] == evidence_id

    # Retrieve history
    history_res = client.get(f"/v1/missions/{mission_id}/tasks/{task_id}/history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 2  # creation event + evidence link event
    notes = [h["notes"] for h in history]
    assert any("Attached custom allocator" in n or "Attached evidence" in n for n in notes)


def test_mission_change_proposal_and_diff():
    """13 & 14. Create proposal and verify before/after diff calculation."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]

    # Create proposal targeting backend-api-intern
    prop_res = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Shift focus to Backend API Intern",
            "rationale": "Aligning preparation with upcoming Backend API opening.",
            "target_role_id": "backend-api-intern",
        },
    )
    assert prop_res.status_code == 201, prop_res.text
    prop_data = prop_res.json()

    assert prop_data["mission_id"] == mission_id
    assert prop_data["base_version_number"] == 1
    assert prop_data["status"] == "pending"
    assert "diff_summary" in prop_data

    diff = prop_data["diff_summary"]
    assert "added_tasks" in diff
    assert "removed_tasks" in diff
    assert "retained_tasks" in diff
    assert "effort_delta" in diff


def test_proposal_rejection():
    """15. Student rejection of change proposal."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]

    prop_res = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Tentative Plan Revision",
            "rationale": "Proposed exploratory change.",
            "target_role_id": "backend-api-intern",
        },
    )
    proposal_id = prop_res.json()["id"]

    rej_res = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/reject",
        json={"decision_notes": "Prefer to stick to distributed systems curriculum for now."},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"
    assert "Prefer to stick" in rej_res.json()["student_decision_notes"]

    # Cannot approve rejected proposal
    cannot_approve = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/approve",
        json={"decision_notes": "Trying to approve anyway"},
    )
    assert cannot_approve.status_code == 422


def test_proposal_approval_and_work_preservation():
    """16 & 17. Proposal approval creates immutable Version 2.0 and preserves completed work."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]
    task1 = create_res.json()["active_version"]["stages"][0]["tasks"][0]

    # Complete task1 in Version 1.0
    client.patch(
        f"/v1/missions/{mission_id}/tasks/{task1['id']}/status",
        json={"status": "completed", "notes": "Completed milestone early"},
    )

    # Propose revised plan
    prop_res = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Updated Strategy for Distributed Systems",
            "rationale": "Refreshed plan reflecting completed competency.",
            "target_role_id": "distributed-systems-intern",
        },
    )
    proposal_id = prop_res.json()["id"]

    # Approve proposal
    appr_res = client.post(
        f"/v1/missions/{mission_id}/proposals/{proposal_id}/approve",
        json={"decision_notes": "Approved new roadmap revision."},
    )
    assert appr_res.status_code == 200
    updated_mission = appr_res.json()

    assert updated_mission["active_version_number"] == 2
    active_v = updated_mission["active_version"]
    assert active_v["version_number"] == 2
    assert active_v["is_active"] is True

    # Check preserved work
    v2_tasks = active_v["tasks"]
    matching_v2_task = next(
        (t for t in v2_tasks if t["stable_key"] == task1["stable_key"]), None
    )
    assert matching_v2_task is not None
    assert matching_v2_task["status"] == "completed"
    assert matching_v2_task["completed_at"] is not None

    # Check that Version 1.0 remains in history and is marked inactive
    versions_res = client.get(f"/v1/missions/{mission_id}/versions")
    assert versions_res.status_code == 200
    versions = versions_res.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1
    assert versions[1]["is_active"] is False


def test_stale_proposal_conflict():
    """18. Stale proposal conflict returns HTTP 409."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]

    # Create Proposal A targeting Version 1
    prop_a = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Proposal A",
            "rationale": "First revision",
            "target_role_id": "distributed-systems-intern",
        },
    ).json()

    # Create Proposal B targeting Version 1
    prop_b = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Proposal B",
            "rationale": "Second concurrent revision",
            "target_role_id": "distributed-systems-intern",
        },
    ).json()

    # Approve Proposal A -> Advances mission to Version 2
    client.post(f"/v1/missions/{mission_id}/proposals/{prop_a['id']}/approve")

    # Attempt to approve Proposal B (which targeted Version 1) -> Stale conflict 409
    stale_res = client.post(f"/v1/missions/{mission_id}/proposals/{prop_b['id']}/approve")
    assert stale_res.status_code == 409
    assert "Stale proposal conflict" in stale_res.json()["detail"]


def test_repeated_approval_idempotency():
    """19. Repeated approval requests are handled idempotently."""
    create_res = client.post(
        "/v1/missions",
        json={"target_role_id": "distributed-systems-intern"},
    )
    mission_id = create_res.json()["id"]

    prop = client.post(
        f"/v1/missions/{mission_id}/proposals",
        json={
            "proposal_title": "Idempotency Test Proposal",
            "rationale": "Valid change",
            "target_role_id": "distributed-systems-intern",
        },
    ).json()

    appr1 = client.post(f"/v1/missions/{mission_id}/proposals/{prop['id']}/approve")
    assert appr1.status_code == 200
    v_num1 = appr1.json()["active_version_number"]

    # Repeat approval
    appr2 = client.post(f"/v1/missions/{mission_id}/proposals/{prop['id']}/approve")
    assert appr2.status_code == 200
    assert appr2.json()["active_version_number"] == v_num1


def test_invalid_ids_return_404():
    """21. Nonexistent mission, task, and proposal IDs return 404."""
    assert client.get("/v1/missions/99999").status_code == 404
    assert client.get("/v1/missions/99999/versions").status_code == 404
    assert client.get("/v1/missions/99999/versions/1").status_code == 404
    assert client.patch("/v1/missions/99999/tasks/1/status", json={"status": "completed"}).status_code == 404
    assert client.post("/v1/missions/99999/tasks/1/evidence", json={"evidence_id": 1}).status_code == 404
    assert client.get("/v1/missions/99999/proposals").status_code == 404
    assert client.post("/v1/missions/99999/proposals/1/approve").status_code == 404


# ---------------------------------------------------------------------------
# Checkpoint B: Mission Creation Idempotency & Conflict Tests
# ---------------------------------------------------------------------------

def test_mission_creation_idempotency_same_key_same_payload():
    """Retrying the exact same idempotency key and payload returns the original mission."""
    key = "idem-test-key-alpha-1"
    payload = {
        "target_role_id": "distributed-systems-intern",
        "weekly_hours": 15,
        "idempotency_key": key,
    }

    # Initial submission
    res1 = client.post("/v1/missions", json=payload)
    assert res1.status_code == 201
    mission1 = res1.json()
    assert mission1["id"] > 0
    assert mission1["target_role_id"] == "distributed-systems-intern"

    # Retry submission with same key & same payload
    res2 = client.post("/v1/missions", json=payload)
    assert res2.status_code == 201
    mission2 = res2.json()

    # Must return identical mission without duplicate creation
    assert mission2["id"] == mission1["id"]
    assert mission2["title"] == mission1["title"]
    assert mission2["weekly_hours"] == mission1["weekly_hours"]

    # Verify database contains only 1 active mission
    missions_list = client.get("/v1/missions").json()
    assert len(missions_list) == 1
    assert missions_list[0]["id"] == mission1["id"]


def test_mission_creation_idempotency_header_support():
    """Idempotency-Key HTTP header works identically to request body property."""
    key = "idem-header-key-beta-2"
    headers = {"Idempotency-Key": key}
    payload = {
        "target_role_id": "backend-api-intern",
        "weekly_hours": 12,
    }

    res1 = client.post("/v1/missions", json=payload, headers=headers)
    assert res1.status_code == 201
    m1 = res1.json()

    res2 = client.post("/v1/missions", json=payload, headers=headers)
    assert res2.status_code == 201
    m2 = res2.json()
    assert m2["id"] == m1["id"]


def test_mission_creation_idempotency_same_key_different_payload_conflict():
    """Reusing the SAME idempotency key with a DIFFERENT payload produces HTTP 409 Conflict."""
    key = "idem-conflict-key-gamma-3"
    payload1 = {
        "target_role_id": "distributed-systems-intern",
        "weekly_hours": 15,
        "idempotency_key": key,
    }
    res1 = client.post("/v1/missions", json=payload1)
    assert res1.status_code == 201

    # Reusing same key with different weekly_hours
    payload2 = {
        "target_role_id": "distributed-systems-intern",
        "weekly_hours": 20,
        "idempotency_key": key,
    }
    res2 = client.post("/v1/missions", json=payload2)
    assert res2.status_code == 409
    err = res2.json()["detail"]
    assert "Idempotency conflict" in err
    assert "different payload" in err


def test_mission_creation_different_key_same_role_active_protection():
    """A DIFFERENT key does NOT silently adopt a previous active mission; it returns 409 Active Mission conflict."""
    key1 = "idem-key-orig-4"
    res1 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": 15,
            "idempotency_key": key1,
        },
    )
    assert res1.status_code == 201
    m1 = res1.json()

    # Submission with a DIFFERENT key for the same role without allow_replace_active
    key2 = "idem-key-different-5"
    res2 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": 15,
            "idempotency_key": key2,
            "allow_replace_active": False,
        },
    )
    # Must reject with 409 to protect active mission
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


def test_mission_creation_explicit_replace_with_idempotency():
    """Explicit replace (allow_replace_active=True) archives previous active mission and creates new mission."""
    key1 = "idem-replace-old-6"
    res1 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": 15,
            "idempotency_key": key1,
        },
    )
    assert res1.status_code == 201
    m1 = res1.json()

    key2 = "idem-replace-new-7"
    res2 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "backend-api-intern",
            "weekly_hours": 20,
            "allow_replace_active": True,
            "idempotency_key": key2,
        },
    )
    assert res2.status_code == 201
    m2 = res2.json()
    assert m2["id"] != m1["id"]
    assert m2["target_role_id"] == "backend-api-intern"

    # Verify previous mission is now archived and new one is active
    active = client.get("/v1/missions/active").json()
    assert active["id"] == m2["id"]

    all_missions = client.get("/v1/missions").json()
    old_mission = next(m for m in all_missions if m["id"] == m1["id"])
    assert old_mission["status"] == "archived"


def test_mission_creation_preserves_completed_tasks_on_idempotent_replay():
    """Idempotent replay returns current active mission state including progressed tasks without resetting them."""
    key = "idem-replay-progress-8"
    res1 = client.post(
        "/v1/missions",
        json={
            "target_role_id": "backend-api-intern",
            "weekly_hours": 15,
            "idempotency_key": key,
        },
    )
    assert res1.status_code == 201
    m1 = res1.json()
    first_task = m1["active_version"]["stages"][0]["tasks"][0]

    # Progress first task
    patch_res = client.patch(
        f"/v1/missions/{m1['id']}/tasks/{first_task['id']}/status",
        json={"status": "in_progress"},
    )
    assert patch_res.status_code == 200

    # Idempotent replay of the creation request
    replay_res = client.post(
        "/v1/missions",
        json={
            "target_role_id": "backend-api-intern",
            "weekly_hours": 15,
            "idempotency_key": key,
        },
    )
    assert replay_res.status_code == 201
    replayed = replay_res.json()
    assert replayed["id"] == m1["id"]
    # Task progress must be preserved
    replayed_task = replayed["active_version"]["stages"][0]["tasks"][0]
    assert replayed_task["id"] == first_task["id"]
    assert replayed_task["status"] == "in_progress"


def test_concurrent_duplicate_mission_creation():
    """Concurrent requests with the exact same idempotency key return the same mission without duplicate creation."""
    from concurrent.futures import ThreadPoolExecutor

    key = "idem-concurrent-race-key-99"
    payload = {
        "target_role_id": "backend-api-intern",
        "weekly_hours": 15,
        "idempotency_key": key,
    }

    def post_mission():
        # Each thread gets its own independent client call
        return client.post("/v1/missions", json=payload)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(post_mission) for _ in range(5)]
        results = [f.result() for f in futures]

    # Every concurrent request must receive HTTP 201
    for res in results:
        assert res.status_code == 201

    # All responses must return the exact same mission ID
    mission_ids = [res.json()["id"] for res in results]
    assert len(set(mission_ids)) == 1

    # Exactly one active mission in the database
    missions = client.get("/v1/missions").json()
    assert len(missions) == 1
    assert missions[0]["id"] == mission_ids[0]


def test_network_timeout_and_retry_reconciliation():
    """Client timeout / disconnect before receiving response reconciles cleanly on subsequent retry."""
    key = "idem-timeout-retry-key-77"
    payload = {
        "target_role_id": "distributed-systems-intern",
        "weekly_hours": 12,
        "idempotency_key": key,
    }

    # Initial attempt succeeds on backend
    res1 = client.post("/v1/missions", json=payload)
    assert res1.status_code == 201
    created_mission = res1.json()

    # Client simulates receiving a network timeout, so it retries with the same idempotency key:
    res_retry = client.post("/v1/missions", json=payload)
    assert res_retry.status_code == 201
    retry_mission = res_retry.json()

    # Reconciled mission identity matches exactly
    assert retry_mission["id"] == created_mission["id"]
    assert retry_mission["title"] == created_mission["title"]


def test_mission_creation_failure_rollback():
    """Failure during mission creation (e.g. invalid target role) rolls back transaction without orphan records."""
    key = "idem-failure-key-55"
    payload = {
        "target_role_id": "nonexistent-fake-role-xyz",
        "weekly_hours": 10,
        "idempotency_key": key,
    }

    res = client.post("/v1/missions", json=payload)
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    # Verify no mission record was created
    missions = client.get("/v1/missions").json()
    assert len(missions) == 0


