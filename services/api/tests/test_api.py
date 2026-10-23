from unittest.mock import patch
import subprocess
from fastapi.testclient import TestClient
from app.main import app
from app.bridge import engine_path, EngineUnavailable

client = TestClient(app)

DEMO_MATCH = {
    "student_levels": [2, 1, 0, 1],
    "required_levels": [2, 2, 1, 1],
    "weights": [5, 4, 3, 2],
    "mandatory": [1, 1, 0, 0],
}


# ---------------------------------------------------------
# Phase 1: Health & Matching Tests (Regression Suite)
# ---------------------------------------------------------

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_match_request():
    bad = {**DEMO_MATCH, "weights": [5]}
    assert client.post("/v1/demo/match", json=bad).status_code == 422


def test_match_end_to_end():
    try:
        engine_path()
    except EngineUnavailable as exc:
        raise AssertionError("Compile the C++ engine first: " + str(exc)) from exc
    response = client.post("/v1/demo/match", json=DEMO_MATCH)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["earned_points"] == 54
    assert out["max_points"] == 84
    assert out["missing_mandatory"] == 1
    assert out["mandatory_requirements_met"] is False
    assert abs(out["coverage_percent"] - 64.29) < 0.01


# ---------------------------------------------------------
# Phase 3.1: Learning Path & Curriculum Endpoints
# ---------------------------------------------------------

def test_get_skills():
    response = client.get("/v1/skills")
    assert response.status_code == 200
    skills = response.json()
    assert len(skills) == 10
    skill_names = {s["name"] for s in skills}
    assert "Programming Foundations" in skill_names
    assert "High-Scale Distributed Systems" in skill_names


def test_get_roles():
    response = client.get("/v1/roles")
    assert response.status_code == 200
    roles = response.json()
    assert len(roles) == 2
    role_ids = {r["role_id"] for r in roles}
    assert "distributed-systems-intern" in role_ids
    assert "backend-api-intern" in role_ids


def test_get_role_requirements():
    response = client.get("/v1/roles/distributed-systems-intern/requirements")
    assert response.status_code == 200
    role_detail = response.json()
    assert role_detail["role_id"] == "distributed-systems-intern"
    assert len(role_detail["requirements"]) >= 2
    skill_ids = [req["skill_id"] for req in role_detail["requirements"]]
    assert 6 in skill_ids  # Distributed Systems skill


def test_get_unknown_role_requirements():
    response = client.get("/v1/roles/quantum-crypto-intern/requirements")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_learning_path_success():
    payload = {
        "role_id": "distributed-systems-intern",
        "student_skills": [
            {"skill_id": 1, "level": 2, "is_verified": True},
            {"skill_id": 2, "level": 2, "is_verified": True},
        ],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["achievable"] is True
    assert 6 in data["target_skills"]
    assert len(data["stages"]) >= 1
    assert data["total_estimated_effort"]["min_hours"] > 0
    assert data["total_estimated_effort"]["max_hours"] > data["total_estimated_effort"]["min_hours"]

    # Verify DSA AlgorithmTrace is present and genuine
    assert "algorithm_trace" in data and data["algorithm_trace"] is not None
    trace = data["algorithm_trace"]
    assert trace["graph_node_count"] == 10
    assert trace["graph_edge_count"] >= 9
    assert trace["execution_time_microseconds"] > 0


def test_generate_learning_path_unknown_role():
    payload = {
        "role_id": "non-existent-role",
        "student_skills": [],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_learning_path_invalid_skill_level():
    payload = {
        "role_id": "distributed-systems-intern",
        "student_skills": [
            {"skill_id": 1, "level": 99, "is_verified": True},  # level > 5 invalid
        ],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 422


def test_generate_learning_path_duplicate_skills():
    payload = {
        "role_id": "distributed-systems-intern",
        "student_skills": [
            {"skill_id": 1, "level": 2, "is_verified": True},
            {"skill_id": 1, "level": 3, "is_verified": False},  # duplicate ID
        ],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 422
    assert "duplicate" in response.text.lower()


def test_generate_learning_path_unknown_skill():
    payload = {
        "role_id": "distributed-systems-intern",
        "student_skills": [
            {"skill_id": 9999, "level": 2, "is_verified": True},  # invalid skill ID
        ],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 422
    assert "does not exist" in response.json()["detail"].lower()


def test_generate_learning_path_already_qualified():
    # Student has mastered all required and prerequisite skills to max level (3 on canonical 0-3 scale)
    student_profile = [
        {"skill_id": i, "level": 3, "is_verified": True}
        for i in range(1, 11)
    ]
    payload = {
        "role_id": "backend-api-intern",
        "student_skills": student_profile,
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["achievable"] is True
    # Student is fully qualified: 0 stages needed
    assert len(data["stages"]) == 0
    assert data["total_estimated_effort"]["min_hours"] == 0
    assert data["total_estimated_effort"]["max_hours"] == 0


def test_generate_learning_path_missing_prerequisites():
    # Absolute beginner: student has zero skills
    payload = {
        "role_id": "backend-api-intern",
        "student_skills": [],
    }
    response = client.post("/v1/learning-path/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["achievable"] is True
    # Prerequisites like Foundations (1), Python (2), SQL (9) must be in closure
    assert 1 in data["prerequisite_closure"]
    assert 2 in data["prerequisite_closure"]
    assert len(data["stages"]) >= 2


def test_generate_learning_path_cpp_process_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["internpath_dsa", "--plan-stdin"],
            returncode=1,
            stdout="",
            stderr="C++ process segmentation fault simulation",
        )
        payload = {
            "role_id": "distributed-systems-intern",
            "student_skills": [],
        }
        response = client.post("/v1/learning-path/generate", json=payload)
        assert response.status_code == 503
        assert "simulation" in response.json()["detail"].lower()


def test_generate_learning_path_malformed_cpp_output():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["internpath_dsa", "--plan-stdin"],
            returncode=0,
            stdout="NOT_VALID_JSON_AT_ALL",
            stderr="",
        )
        payload = {
            "role_id": "distributed-systems-intern",
            "student_skills": [],
        }
        response = client.post("/v1/learning-path/generate", json=payload)
        assert response.status_code == 503
        assert "malformed" in response.json()["detail"].lower()


# ---------------------------------------------------------
# Phase 3.2: Persistence, Profile & Integrity Tests
# ---------------------------------------------------------

def test_get_profile():
    response = client.get("/v1/profile")
    assert response.status_code == 200
    profile = response.json()
    assert profile["email"] == "alex.dev@internpath.local"
    assert "Alex Chen" in profile["name"]
    assert len(profile["skills"]) >= 3
    assert profile["is_demo"] is True


def test_update_profile_and_persist():
    # 1. Update student profile
    update_payload = {
        "name": "Alex Chen (Updated)",
        "weekly_hours": 20,
        "target_role_id": "backend-api-intern",
        "skills": [
            {"skill_id": 1, "declared_level": 3, "verified_level": 3, "is_verified": True},
            {"skill_id": 4, "declared_level": 2, "verified_level": 1, "is_verified": True},
        ],
    }
    response = client.put("/v1/profile", json=update_payload)
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Alex Chen (Updated)"
    assert updated["weekly_hours"] == 20
    assert updated["target_role_id"] == "backend-api-intern"

    # 2. Verify persistence on subsequent GET
    get_res = client.get("/v1/profile")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["name"] == "Alex Chen (Updated)"
    assert fetched["weekly_hours"] == 20
    skill_map = {s["skill_id"]: s for s in fetched["skills"]}
    assert skill_map[1]["declared_level"] == 3
    assert skill_map[4]["declared_level"] == 2

    # 3. Cleanly restore default dev profile
    client.put("/v1/profile", json={
        "name": "Alex Chen (Dev Mode)",
        "weekly_hours": 15,
        "target_role_id": "distributed-systems-intern",
    })


def test_update_profile_preserves_verified_status():
    # 1. Inspect existing verified status for skill 1 (verified at level 3)
    prof1 = client.get("/v1/profile").json()
    s1 = next(s for s in prof1["skills"] if s["skill_id"] == 1)
    assert s1["is_verified"] is True
    initial_ver_lvl = s1["verified_level"]

    # 2. Student self-assessment attempts to downgrade or clear verification flags
    client.put("/v1/profile", json={
        "skills": [
            {"skill_id": 1, "declared_level": 2, "verified_level": 0, "is_verified": False},
        ]
    })
    prof2 = client.get("/v1/profile").json()
    s2 = next(s for s in prof2["skills"] if s["skill_id"] == 1)
    # Declared level is updated by student
    assert s2["declared_level"] == 2
    # Verified status and level MUST be preserved (cannot be silently downgraded or erased)
    assert s2["is_verified"] is True
    assert s2["verified_level"] == initial_ver_lvl


def test_update_profile_invalid_level():
    bad_payload = {
        "skills": [
            {"skill_id": 1, "declared_level": 4, "is_verified": False},  # Level 4 > 3 is invalid
        ]
    }
    response = client.put("/v1/profile", json=bad_payload)
    assert response.status_code == 422


def test_evidence_create_and_fetch():
    new_ev = {
        "skill_id": 3,
        "title": "Custom Memory Allocator",
        "description": "Implemented free-list allocator in C++20 with unit tests",
        "url": "https://github.com/alexchen/allocator",
        "evidence_type": "project",
    }
    create_res = client.post("/v1/evidence", json=new_ev)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["title"] == "Custom Memory Allocator"
    assert created["skill_id"] == 3

    # Fetch evidence list
    list_res = client.get("/v1/evidence")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(item["title"] == "Custom Memory Allocator" for item in items)


def test_prerequisite_cycle_prevention():
    import pytest
    from app.database import SessionLocal
    from app.crud import validate_no_prerequisite_cycles

    with SessionLocal() as db:
        # Existing edge: 1 -> 2 (Foundations -> Python) and 2 -> 4 (Python -> FastAPI)
        # Attempting to add 4 -> 1 would form a cycle 1 -> 2 -> 4 -> 1
        with pytest.raises(ValueError, match="cycle detected"):
            validate_no_prerequisite_cycles(db, prerequisite_id=4, skill_id=1)

        # Self-dependency: 1 -> 1
        with pytest.raises(ValueError, match="Self-prerequisite detected"):
            validate_no_prerequisite_cycles(db, prerequisite_id=1, skill_id=1)


def test_database_migration_schema():
    from sqlalchemy import inspect
    from app.database import engine

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "students",
        "skills",
        "student_skills",
        "evidence_items",
        "roles",
        "role_requirements",
        "skill_prerequisites",
    }
    for tbl in expected_tables:
        assert tbl in table_names, f"Table {tbl} must exist in database schema"

    # Verify unique constraints on student_skills
    uq_constraints = inspector.get_unique_constraints("student_skills")
    uq_cols = [c["column_names"] for c in uq_constraints]
    assert ["student_id", "skill_id"] in uq_cols or any(
        set(cols) == {"student_id", "skill_id"} for cols in uq_cols
    )


def test_seed_database_idempotency_and_reset():
    from app.database import SessionLocal
    from app.seed import seed_database
    from app.models import Skill, Role, SkillPrerequisite, Student

    with SessionLocal() as db:
        # Test reset and reseed
        seed_database(db, reset=True)
        assert db.query(Skill).count() == 10
        assert db.query(Role).count() == 2
        assert db.query(SkillPrerequisite).count() == 9
        assert db.query(Student).count() == 1

        # Test idempotency (running seed again without reset should not duplicate records)
        seed_database(db, reset=False)
        assert db.query(Skill).count() == 10
        assert db.query(Role).count() == 2
        assert db.query(SkillPrerequisite).count() == 9


def test_persistence_across_sessions():
    from app.database import SessionLocal
    from app.models import Student

    # Session 1: Update target role and hours
    with SessionLocal() as db1:
        st1 = db1.query(Student).filter(Student.email == "alex.dev@internpath.local").first()
        assert st1 is not None
        st1.weekly_hours = 22
        db1.commit()

    # Session 2: Fresh independent session verifying persistence
    with SessionLocal() as db2:
        st2 = db2.query(Student).filter(Student.email == "alex.dev@internpath.local").first()
        assert st2 is not None
        assert st2.weekly_hours == 22

    # Cleanly restore
    with SessionLocal() as db3:
        st3 = db3.query(Student).filter(Student.email == "alex.dev@internpath.local").first()
        st3.weekly_hours = 15
        db3.commit()


def test_update_profile_negative_level():
    bad_payload = {
        "skills": [
            {"skill_id": 1, "declared_level": -1, "is_verified": False},
        ]
    }
    response = client.put("/v1/profile", json=bad_payload)
    assert response.status_code == 422


def test_update_profile_unknown_skill_id():
    bad_payload = {
        "skills": [
            {"skill_id": 88888, "declared_level": 2, "is_verified": False},
        ]
    }
    response = client.put("/v1/profile", json=bad_payload)
    assert response.status_code == 422
    assert "does not exist" in response.json()["detail"].lower()


def test_duplicate_student_skill_constraint():
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.database import SessionLocal
    from app.models import StudentSkill, Student

    with SessionLocal() as db:
        student = db.query(Student).filter(Student.email == "alex.dev@internpath.local").first()
        assert student is not None
        # Attempt to insert an existing skill directly bypassing API logic
        dup = StudentSkill(
            student_id=student.id,
            skill_id=1,
            declared_level=2,
            verified_level=2,
            is_verified=True,
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_role_requirement_constraints():
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.database import SessionLocal
    from app.models import RoleRequirement

    with SessionLocal() as db:
        # Invalid required_level = 5 (violates ck_required_level_range 1..3)
        bad_req = RoleRequirement(
            role_id="backend-api-intern",
            skill_id=1,
            required_level=5,
            mandatory=True,
            role_context="Invalid constraint test",
        )
        db.add(bad_req)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_transaction_rollback_on_failure():
    from app.database import SessionLocal
    from app.models import Student
    from app.crud import update_student_profile

    with SessionLocal() as db:
        student = db.query(Student).filter(Student.email == "alex.dev@internpath.local").first()
        assert student is not None
        original_name = student.name

        # Attempt atomic update where one item is invalid
        try:
            update_student_profile(
                db,
                student_id=student.id,
                name="Should Not Be Persisted",
                skills_data=[
                    {"skill_id": 1, "declared_level": 2},
                    {"skill_id": 99999, "declared_level": 2},  # Nonexistent
                ],
            )
        except ValueError:
            db.rollback()

        # Verify rollback preserved original student name
        refreshed = db.query(Student).filter(Student.id == student.id).first()
        assert refreshed.name == original_name


def test_database_to_cpp_transport_direct():
    from app.database import SessionLocal
    from app import crud
    from app.bridge import run_learning_path_with_graph
    from app.schemas import TargetSkillInput, StudentSkillInput

    with SessionLocal() as db:
        skills = crud.get_skills(db)
        prereqs = crud.get_all_prerequisites(db)

        targets = [TargetSkillInput(skill_id=6, required_level=3)]
        student = [
            StudentSkillInput(skill_id=1, level=2, is_verified=True),
            StudentSkillInput(skill_id=2, level=2, is_verified=True),
        ]

        plan = run_learning_path_with_graph(
            skills=skills,
            prerequisites=prereqs,
            targets=targets,
            student=student,
        )
        assert plan.achievable is True
        assert 6 in plan.target_skills
        assert plan.algorithm_trace is not None
        assert plan.algorithm_trace.execution_time_microseconds > 0


def test_cpp_subprocess_timeout():
    from unittest.mock import patch
    import subprocess

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["internpath_dsa", "--plan-stdin"], timeout=5)
        payload = {
            "role_id": "distributed-systems-intern",
            "student_skills": [],
        }
        response = client.post("/v1/learning-path/generate", json=payload)
        assert response.status_code == 503
        assert "execute" in response.json()["detail"].lower()


