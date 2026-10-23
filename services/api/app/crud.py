"""Data access layer for InternPath persistent database.

Handles querying skills, roles, curriculum graph relationships,
student profile persistence, evidence items, and cycle detection.
"""
import json
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.agent.clock import get_naive_utc_now, get_utc_now

from .models import (
    Student,
    Skill,
    StudentSkill,
    EvidenceItem,
    Role,
    RoleRequirement,
    SkillPrerequisite,
    CareerMission,
    MissionVersion,
    MissionTask,
    TaskProgressEvent,
    MissionChangeProposal,
)

DEV_STUDENT_EMAIL = "alex.dev@internpath.local"
DEV_STUDENT_NAME = "Alex Chen (Dev Mode)"


# ---------------------------------------------------------------------------
# Skills & Curriculum Graph
# ---------------------------------------------------------------------------

def get_skills(db: Session) -> list[dict[str, Any]]:
    """Return all skills ordered by id with prerequisite & unlocked arrays."""
    skills = db.query(Skill).order_by(Skill.id).all()
    prereq_edges = db.query(SkillPrerequisite).all()

    # Build adjacency lists:
    # prereq -> skill means prereq is required before skill
    prereq_map: dict[int, list[int]] = {s.id: [] for s in skills}
    unlocked_map: dict[int, list[int]] = {s.id: [] for s in skills}

    for edge in prereq_edges:
        if edge.skill_id in prereq_map:
            prereq_map[edge.skill_id].append(edge.prerequisite_id)
        if edge.prerequisite_id in unlocked_map:
            unlocked_map[edge.prerequisite_id].append(edge.skill_id)

    results = []
    for s in skills:
        results.append({
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "max_level": s.max_level,
            "description": s.description,
            "prerequisites": sorted(prereq_map.get(s.id, [])),
            "unlocked_skills": sorted(unlocked_map.get(s.id, [])),
        })
    return results


def get_skill_by_id(db: Session, skill_id: int) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.id == skill_id).first()


def get_all_prerequisites(db: Session) -> list[tuple[int, int]]:
    """Return list of (prerequisite_id, skill_id) directed edges."""
    edges = db.query(SkillPrerequisite).all()
    return [(e.prerequisite_id, e.skill_id) for e in edges]


def validate_no_prerequisite_cycles(db: Session, prerequisite_id: int, skill_id: int) -> None:
    """Validate that adding a directed edge prerequisite_id -> skill_id does not form a cycle.

    A cycle would occur if there already exists a path from skill_id to prerequisite_id.
    """
    if prerequisite_id == skill_id:
        raise ValueError(f"Self-prerequisite detected: skill {skill_id} cannot depend on itself.")

    # Fetch existing edges
    edges = db.query(SkillPrerequisite.prerequisite_id, SkillPrerequisite.skill_id).all()
    adj: dict[int, list[int]] = {}
    for p_id, s_id in edges:
        adj.setdefault(p_id, []).append(s_id)

    # Check reachability from skill_id to prerequisite_id (DFS)
    visited: set[int] = set()
    stack: list[int] = [skill_id]

    while stack:
        curr = stack.pop()
        if curr == prerequisite_id:
            raise ValueError(
                f"Prerequisite cycle detected: adding {prerequisite_id} -> {skill_id} creates a circular dependency."
            )
        if curr not in visited:
            visited.add(curr)
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    stack.append(neighbor)


# ---------------------------------------------------------------------------
# Roles & Requirements
# ---------------------------------------------------------------------------

def get_roles(db: Session) -> list[dict[str, Any]]:
    """Return all roles with count of requirements."""
    roles = db.query(Role).order_by(Role.id).all()
    results = []
    for r in roles:
        results.append({
            "role_id": r.role_id,
            "title": r.title,
            "department": r.department,
            "location": r.location,
            "description": r.description,
            "requirements_count": len(r.requirements),
        })
    return results


def get_role_by_id(db: Session, role_id: str) -> Optional[Role]:
    return db.query(Role).filter(Role.role_id == role_id).first()


def get_role_requirements(db: Session, role_id: str) -> list[dict[str, Any]]:
    """Return competency requirements for a target role."""
    reqs = (
        db.query(RoleRequirement, Skill)
        .join(Skill, RoleRequirement.skill_id == Skill.id)
        .filter(RoleRequirement.role_id == role_id)
        .all()
    )
    return [
        {
            "skill_id": rr.skill_id,
            "skill_name": sk.name,
            "required_level": rr.required_level,
            "mandatory": rr.mandatory,
            "role_context": rr.role_context,
        }
        for rr, sk in reqs
    ]



# ---------------------------------------------------------------------------
# Student Profile & Skills
# ---------------------------------------------------------------------------

def get_or_create_dev_student(db: Session) -> Student:
    """Get the active development student profile or create default if not present."""
    student = db.query(Student).filter(Student.email == DEV_STUDENT_EMAIL).first()
    if not student:
        student = Student(
            name=DEV_STUDENT_NAME,
            email=DEV_STUDENT_EMAIL,
            target_role_id="distributed-systems-intern",
            weekly_hours=12,
            is_demo=True,
        )
        db.add(student)
        db.commit()
        db.refresh(student)

        # Add initial sample skills: Skill 1 (L2), Skill 2 (L2), Skill 7 (L1)
        sample_skills = [
            (1, 2, 2, True),
            (2, 2, 2, True),
            (7, 1, 0, False),
        ]
        for sid, decl, ver, is_v in sample_skills:
            db.add(StudentSkill(
                student_id=student.id,
                skill_id=sid,
                declared_level=decl,
                verified_level=ver,
                is_verified=is_v,
            ))
        db.commit()
        db.refresh(student)
    return student


def get_student_skills(db: Session, student_id: int) -> list[dict[str, Any]]:
    """Return list of skill competence records for a student."""
    skills_records = (
        db.query(StudentSkill, Skill)
        .join(Skill, StudentSkill.skill_id == Skill.id)
        .filter(StudentSkill.student_id == student_id)
        .all()
    )
    results = []
    for ss, sk in skills_records:
        results.append({
            "skill_id": ss.skill_id,
            "skill_name": sk.name,
            "category": sk.category,
            "declared_level": ss.declared_level,
            "verified_level": ss.verified_level,
            "is_verified": ss.is_verified,
            "updated_at": ss.updated_at.isoformat() if ss.updated_at else None,
        })
    return results


def get_student_profile(db: Session, student_id: int) -> Optional[dict[str, Any]]:
    """Return complete structured student profile."""

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return None

    skills_records = (
        db.query(StudentSkill, Skill)
        .join(Skill, StudentSkill.skill_id == Skill.id)
        .filter(StudentSkill.student_id == student_id)
        .all()
    )

    formatted_skills = []
    for ss, sk in skills_records:
        formatted_skills.append({
            "skill_id": ss.skill_id,
            "skill_name": sk.name,
            "category": sk.category,
            "declared_level": ss.declared_level,
            "verified_level": ss.verified_level,
            "is_verified": ss.is_verified,
            "updated_at": ss.updated_at.isoformat() if ss.updated_at else None,
        })

    evidence_records = (
        db.query(EvidenceItem, Skill)
        .join(Skill, EvidenceItem.skill_id == Skill.id)
        .filter(EvidenceItem.student_id == student_id)
        .order_by(EvidenceItem.created_at.desc())
        .all()
    )

    formatted_evidence = []
    for ev, sk in evidence_records:
        formatted_evidence.append({
            "id": ev.id,
            "skill_id": ev.skill_id,
            "skill_name": sk.name,
            "title": ev.title,
            "description": ev.description,
            "url": ev.url,
            "evidence_type": ev.evidence_type,
            "verified_by_staff": ev.verified_by_staff,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "target_role_id": student.target_role_id,
        "weekly_hours": student.weekly_hours,
        "is_demo": student.is_demo,
        "skills": formatted_skills,
        "evidence": formatted_evidence,
    }


def update_student_profile(
    db: Session,
    student_id: int,
    name: Optional[str] = None,
    target_role_id: Optional[str] = None,
    weekly_hours: Optional[int] = None,
    skills_data: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Atomically update student profile attributes and skills."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student with ID {student_id} not found.")

    if name is not None:
        student.name = name
    if target_role_id is not None:
        # Validate role exists
        if target_role_id:
            role = db.query(Role).filter(Role.role_id == target_role_id).first()
            if not role:
                raise ValueError(f"Role '{target_role_id}' does not exist.")
        student.target_role_id = target_role_id
    if weekly_hours is not None:
        if weekly_hours < 1 or weekly_hours > 80:
            raise ValueError("weekly_hours must be between 1 and 80.")
        student.weekly_hours = weekly_hours

    if skills_data is not None:
        # Validate all skills exist
        skill_ids = [s["skill_id"] for s in skills_data]
        existing_skills = db.query(Skill.id).filter(Skill.id.in_(skill_ids)).all()
        existing_ids = {s[0] for s in existing_skills}
        for sid in skill_ids:
            if sid not in existing_ids:
                raise ValueError(f"Skill ID {sid} does not exist.")

        # Update or insert skill records
        current_skills = {
            ss.skill_id: ss
            for ss in db.query(StudentSkill).filter(StudentSkill.student_id == student_id).all()
        }

        for item in skills_data:
            sid = item["skill_id"]
            lvl = item.get("declared_level", item.get("level", 0))

            if lvl is None:
                lvl = 0
            is_ver = bool(item.get("is_verified", False))
            ver_lvl = item.get("verified_level")
            if ver_lvl is None:
                ver_lvl = lvl if is_ver else 0

            if not 0 <= lvl <= 3:
                raise ValueError(f"Declared level for skill {sid} must be between 0 and 3.")
            if not 0 <= ver_lvl <= 3:
                raise ValueError(f"Verified level for skill {sid} must be between 0 and 3.")


            if sid in current_skills:
                rec = current_skills[sid]
                rec.declared_level = lvl
                rec.verified_level = ver_lvl
                rec.is_verified = is_ver
            else:
                new_rec = StudentSkill(
                    student_id=student_id,
                    skill_id=sid,
                    declared_level=lvl,
                    verified_level=ver_lvl,
                    is_verified=is_ver,
                )
                db.add(new_rec)

    db.commit()
    return get_student_profile(db, student_id)  # type: ignore


# ---------------------------------------------------------------------------
# Evidence Management
# ---------------------------------------------------------------------------

def add_evidence(
    db: Session,
    student_id: int,
    skill_id: int,
    title: str,
    description: str = "",
    url: Optional[str] = None,
    evidence_type: str = "project",
) -> EvidenceItem:
    """Create a supporting evidence item."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student ID {student_id} not found.")

    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise ValueError(f"Skill ID {skill_id} not found.")

    item = EvidenceItem(
        student_id=student_id,
        skill_id=skill_id,
        title=title,
        description=description,
        url=url,
        evidence_type=evidence_type,
        verified_by_staff=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_evidence_for_student(db: Session, student_id: int) -> list[dict[str, Any]]:
    records = (
        db.query(EvidenceItem, Skill)
        .join(Skill, EvidenceItem.skill_id == Skill.id)
        .filter(EvidenceItem.student_id == student_id)
        .order_by(EvidenceItem.created_at.desc())
        .all()
    )
    return [
        {
            "id": ev.id,
            "skill_id": ev.skill_id,
            "skill_name": sk.name,
            "title": ev.title,
            "description": ev.description,
            "url": ev.url,
            "evidence_type": ev.evidence_type,
            "verified_by_staff": ev.verified_by_staff,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev, sk in records
    ]


# ---------------------------------------------------------------------------
# Phase 3.3: Career Mission & Plan Versioning Engine
# ---------------------------------------------------------------------------

def generate_completion_criteria(skill_name: str, category: str, target_level: int) -> str:
    """Generate clear, measurable, deterministic completion criteria for a competency milestone."""
    level_labels = {1: "Foundational / Basic", 2: "Intermediate Working", 3: "Advanced Production-Ready"}
    lvl_str = level_labels.get(target_level, f"Level {target_level}")

    if target_level <= 1:
        return (
            f"Achieve foundational competence in {skill_name} ({category}): "
            f"study essential syntax and architectural principles, complete introductory modules, "
            f"and verify understanding by completing unit assessments or core coursework."
        )
    elif target_level == 2:
        return (
            f"Demonstrate working competence in {skill_name} ({lvl_str}): "
            f"implement functional, modular software components with automated tests, handle edge cases, "
            f"and upload portfolio code demonstrating practical application in {category} workflows."
        )
    else:
        return (
            f"Attain production-level mastery in {skill_name} ({lvl_str}): "
            f"design scalable architecture, benchmark performance against constraints, "
            f"and deliver verified test suites, technical writeups, or industry-grade portfolio artifacts."
        )


def build_task_stable_key(skill_id: int, target_level: int) -> str:
    return f"task_skill_{skill_id}_lvl_{target_level}"


def is_task_unlocked(prereq_keys: list[str], tasks_by_key: dict[str, MissionTask]) -> bool:
    """A task is unlocked if all its prerequisite tasks in the same version are in 'completed' state."""
    if not prereq_keys:
        return True
    for pkey in prereq_keys:
        prereq_task = tasks_by_key.get(pkey)
        if not prereq_task or prereq_task.status != "completed":
            return False
    return True


def format_task_dict(task: MissionTask, is_unlocked: bool) -> dict[str, Any]:
    prereqs = []
    if task.prerequisite_task_keys:
        try:
            prereqs = json.loads(task.prerequisite_task_keys)
        except Exception:
            prereqs = []

    return {
        "id": task.id,
        "version_id": task.version_id,
        "stable_key": task.stable_key,
        "stage_number": task.stage_number,
        "stage_title": task.stage_title,
        "skill_id": task.skill_id,
        "skill_name": task.skill_name,
        "category": task.category,
        "current_level": task.current_level,
        "target_level": task.target_level,
        "level_delta": task.level_delta,
        "status": task.status,
        "is_unlocked": is_unlocked,
        "estimated_hours_min": task.estimated_hours_min,
        "estimated_hours_max": task.estimated_hours_max,
        "completion_criteria": task.completion_criteria,
        "rationale": task.rationale,
        "prerequisite_task_keys": prereqs,
        "evidence_id": task.evidence_id,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "completed_by": task.completed_by,
        "override_reason": task.override_reason,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def format_mission_version_dict(
    version: MissionVersion,
) -> dict[str, Any]:
    tasks_by_key = {t.stable_key: t for t in version.tasks}
    stages_map: dict[int, dict[str, Any]] = {}

    formatted_tasks = []
    completed_count = 0

    for t in sorted(version.tasks, key=lambda x: (x.stage_number, x.id)):
        prereqs = []
        if t.prerequisite_task_keys:
            try:
                prereqs = json.loads(t.prerequisite_task_keys)
            except Exception:
                prereqs = []
        unlocked = is_task_unlocked(prereqs, tasks_by_key)
        tdict = format_task_dict(t, unlocked)
        formatted_tasks.append(tdict)

        if t.status == "completed":
            completed_count += 1

        stage_num = t.stage_number
        if stage_num not in stages_map:
            stages_map[stage_num] = {
                "stage_number": stage_num,
                "stage_title": t.stage_title,
                "total_tasks": 0,
                "completed_tasks": 0,
                "stage_hours_min": 0,
                "stage_hours_max": 0,
                "tasks": [],
            }
        stages_map[stage_num]["total_tasks"] += 1
        if t.status == "completed":
            stages_map[stage_num]["completed_tasks"] += 1
        stages_map[stage_num]["stage_hours_min"] += t.estimated_hours_min
        stages_map[stage_num]["stage_hours_max"] += t.estimated_hours_max
        stages_map[stage_num]["tasks"].append(tdict)

    sorted_stages = [stages_map[k] for k in sorted(stages_map.keys())]

    return {
        "id": version.id,
        "mission_id": version.mission_id,
        "version_number": version.version_number,
        "title": version.title,
        "rationale": version.rationale,
        "source_schema_version": version.source_schema_version,
        "is_active": version.is_active,
        "created_by": version.created_by,
        "approved_by": version.approved_by,
        "approved_at": version.approved_at.isoformat() if version.approved_at else None,
        "total_estimated_hours_min": version.total_estimated_hours_min,
        "total_estimated_hours_max": version.total_estimated_hours_max,
        "total_tasks": len(version.tasks),
        "completed_tasks": completed_count,
        "stages": sorted_stages,
        "tasks": formatted_tasks,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def format_career_mission_dict(mission: CareerMission) -> dict[str, Any]:
    active_v = mission.active_version
    active_version_data = format_mission_version_dict(active_v) if active_v else None

    total_tasks = active_version_data["total_tasks"] if active_version_data else 0
    completed_tasks = active_version_data["completed_tasks"] if active_version_data else 0
    in_prog = sum(1 for t in (active_v.tasks if active_v else []) if t.status == "in_progress")

    progress_pct = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 0.0

    rem_min = sum(
        t.estimated_hours_min
        for t in (active_v.tasks if active_v else [])
        if t.status != "completed"
    )
    rem_max = sum(
        t.estimated_hours_max
        for t in (active_v.tasks if active_v else [])
        if t.status != "completed"
    )

    pending_proposals = sum(1 for p in mission.proposals if p.status == "pending")

    return {
        "id": mission.id,
        "student_id": mission.student_id,
        "target_role_id": mission.target_role_id,
        "target_role_title": mission.target_role.title if mission.target_role else None,
        "title": mission.title,
        "status": mission.status,
        "weekly_hours": mission.weekly_hours,
        "active_version_number": active_v.version_number if active_v else None,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "in_progress_tasks": in_prog,
        "progress_percent": round(progress_pct, 1),
        "estimated_remaining_hours_min": rem_min,
        "estimated_remaining_hours_max": rem_max,
        "active_version": active_version_data,
        "pending_proposals_count": pending_proposals,
        "created_at": mission.created_at.isoformat() if mission.created_at else None,
        "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
    }


def create_career_mission_from_plan(
    db: Session,
    student_id: int,
    plan_data: dict[str, Any],
    target_role_id: Optional[str] = None,
    title: Optional[str] = None,
    weekly_hours: Optional[int] = None,
    allow_replace_active: bool = False,
) -> CareerMission:
    """Create a persistent Career Mission, its immutable initial Version 1, and ordered tasks."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student ID {student_id} not found.")

    role_title = "Custom Competency Plan"
    if target_role_id:
        role = db.query(Role).filter(Role.role_id == target_role_id).first()
        if role:
            role_title = role.title

    if not plan_data.get("achievable", False):
        raise ValueError(
            f"Cannot create Career Mission: Plan is not achievable ({plan_data.get('message', 'Unmet prerequisites')})."
        )

    # Check for existing active mission with this role
    existing_active = (
        db.query(CareerMission)
        .filter(
            CareerMission.student_id == student_id,
            CareerMission.status == "active",
        )
        .first()
    )

    if existing_active and not allow_replace_active:
        if existing_active.target_role_id == target_role_id:
            raise ValueError(
                f"An active Career Mission already exists for '{role_title}'. "
                f"Please view your existing active mission or propose a plan revision."
            )
        else:
            # Archive previous active mission if student initiates a new target role mission
            existing_active.status = "archived"

    hours = weekly_hours or student.weekly_hours or 10
    mission_title = title or f"Career Mission: {role_title}"

    total_effort = plan_data.get("total_estimated_effort", {})
    min_hours = total_effort.get("min_hours", 0)
    max_hours = total_effort.get("max_hours", 0)

    # 1. Create Mission
    mission = CareerMission(
        student_id=student_id,
        target_role_id=target_role_id,
        title=mission_title,
        status="active",
        weekly_hours=hours,
        engine_metadata=json.dumps(plan_data.get("algorithm_trace") or {}),
    )
    db.add(mission)
    db.flush()

    # 2. Create Version 1.0 (Initial approved version)
    version = MissionVersion(
        mission_id=mission.id,
        version_number=1,
        title=f"Version 1.0 — Initial Approved Plan for {role_title}",
        rationale=(
            f"Generated from C++20 LearningPathEngine topological plan for {role_title}. "
            f"Prerequisite closure verified, organized into {len(plan_data.get('stages', []))} parallelizable stages."
        ),
        source_schema_version="v1.0",
        plan_snapshot=json.dumps(plan_data),
        is_active=True,
        created_by="system_planner",
        approved_by=student.email,
        approved_at=get_naive_utc_now(),
        total_estimated_hours_min=min_hours,
        total_estimated_hours_max=max_hours,
    )
    db.add(version)
    db.flush()

    # Map skills in plan to their stages to determine intra-plan prerequisite task dependencies
    # We query the DAG prerequisites to know which prior-stage tasks this task depends on.
    prereq_edges = db.query(SkillPrerequisite).all()
    # prereq_map: skill_id -> list of prerequisite_ids
    prereq_graph: dict[int, list[int]] = {}
    for edge in prereq_edges:
        prereq_graph.setdefault(edge.skill_id, []).append(edge.prerequisite_id)

    # Map of all task stable keys in plan: skill_id -> stable_key
    all_plan_skill_keys: dict[int, str] = {}
    for stage in plan_data.get("stages", []):
        for sk in stage.get("skills", []):
            stable_key = build_task_stable_key(sk["skill_id"], sk["target_level"])
            all_plan_skill_keys[sk["skill_id"]] = stable_key

    # 3. Create Tasks
    for stage in plan_data.get("stages", []):
        stage_num = stage.get("stage_number", 1)
        stage_title = stage.get("stage_title", f"Stage {stage_num}")

        for sk in stage.get("skills", []):
            skill_id = sk["skill_id"]
            target_level = sk["target_level"]
            stable_key = build_task_stable_key(skill_id, target_level)

            # Determine task prerequisites:
            # Any skill prerequisite that is present in the plan in an earlier or same stage
            task_prereq_keys = []
            for p_id in prereq_graph.get(skill_id, []):
                if p_id in all_plan_skill_keys and p_id != skill_id:
                    task_prereq_keys.append(all_plan_skill_keys[p_id])

            effort = sk.get("estimated_effort", {})
            criteria = generate_completion_criteria(sk["skill_name"], sk["category"], target_level)

            task = MissionTask(
                version_id=version.id,
                stable_key=stable_key,
                stage_number=stage_num,
                stage_title=stage_title,
                skill_id=skill_id,
                skill_name=sk["skill_name"],
                category=sk["category"],
                current_level=sk.get("current_level", 0),
                target_level=target_level,
                level_delta=sk.get("level_delta", 1),
                status="not_started",
                estimated_hours_min=effort.get("min_hours", 0),
                estimated_hours_max=effort.get("max_hours", 0),
                completion_criteria=criteria,
                rationale=sk.get("rationale", ""),
                prerequisite_task_keys=json.dumps(sorted(list(set(task_prereq_keys)))),
            )
            db.add(task)
            db.flush()

            # Record creation event
            init_event = TaskProgressEvent(
                task_id=task.id,
                from_status="none",
                to_status="not_started",
                notes="Task initialized with approved Version 1.0 Career Mission.",
                actor="system_planner",
            )
            db.add(init_event)

    db.commit()
    db.refresh(mission)
    return mission


def get_career_missions_for_student(db: Session, student_id: int) -> list[dict[str, Any]]:
    missions = (
        db.query(CareerMission)
        .filter(CareerMission.student_id == student_id)
        .order_by(CareerMission.created_at.desc())
        .all()
    )
    results = []
    for m in missions:
        active_v = m.active_version
        v_data = format_mission_version_dict(active_v) if active_v else None
        total_t = v_data["total_tasks"] if v_data else 0
        comp_t = v_data["completed_tasks"] if v_data else 0
        pct = (comp_t / total_t * 100.0) if total_t > 0 else 0.0

        results.append({
            "id": m.id,
            "student_id": m.student_id,
            "target_role_id": m.target_role_id,
            "target_role_title": m.target_role.title if m.target_role else None,
            "title": m.title,
            "status": m.status,
            "weekly_hours": m.weekly_hours,
            "active_version_number": active_v.version_number if active_v else None,
            "progress_percent": round(pct, 1),
            "total_tasks": total_t,
            "completed_tasks": comp_t,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return results


def get_active_career_mission(db: Session, student_id: int) -> Optional[CareerMission]:
    return (
        db.query(CareerMission)
        .filter(
            CareerMission.student_id == student_id,
            CareerMission.status == "active",
        )
        .order_by(CareerMission.created_at.desc())
        .first()
    )


def get_career_mission_by_id(
    db: Session, mission_id: int, student_id: int
) -> Optional[CareerMission]:
    return (
        db.query(CareerMission)
        .filter(
            CareerMission.id == mission_id,
            CareerMission.student_id == student_id,
        )
        .first()
    )


def get_mission_versions(
    db: Session, mission_id: int, student_id: int
) -> list[dict[str, Any]]:
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    versions = (
        db.query(MissionVersion)
        .filter(MissionVersion.mission_id == mission_id)
        .order_by(MissionVersion.version_number.desc())
        .all()
    )

    results = []
    for v in versions:
        results.append({
            "id": v.id,
            "mission_id": v.mission_id,
            "version_number": v.version_number,
            "title": v.title,
            "rationale": v.rationale,
            "is_active": v.is_active,
            "created_by": v.created_by,
            "approved_by": v.approved_by,
            "approved_at": v.approved_at.isoformat() if v.approved_at else None,
            "total_estimated_hours_min": v.total_estimated_hours_min,
            "total_estimated_hours_max": v.total_estimated_hours_max,
            "total_tasks": len(v.tasks),
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })
    return results


def get_mission_version_detail(
    db: Session, mission_id: int, version_number: int, student_id: int
) -> Optional[dict[str, Any]]:
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    version = (
        db.query(MissionVersion)
        .filter(
            MissionVersion.mission_id == mission_id,
            MissionVersion.version_number == version_number,
        )
        .first()
    )
    if not version:
        return None

    return format_mission_version_dict(version)


def update_mission_task_status(
    db: Session,
    mission_id: int,
    task_id: int,
    student_id: int,
    new_status: str,
    override_reason: Optional[str] = None,
    notes: str = "",
    actor: str = "student",
) -> dict[str, Any]:
    """Safely advance or modify task status with prerequisite dependency checks."""
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    active_v = mission.active_version
    if not active_v:
        raise ValueError("Mission has no active version.")

    task = (
        db.query(MissionTask)
        .filter(
            MissionTask.id == task_id,
            MissionTask.version_id == active_v.id,
        )
        .first()
    )
    if not task:
        raise ValueError(f"Task ID {task_id} not found in active version {active_v.version_number}.")

    if new_status not in ("not_started", "in_progress", "completed"):
        raise ValueError(f"Invalid status '{new_status}'. Must be not_started, in_progress, or completed.")

    old_status = task.status
    if old_status == new_status:
        # Idempotent status update
        return format_task_dict(task, is_unlocked=True)

    tasks_by_key = {t.stable_key: t for t in active_v.tasks}
    prereqs = []
    if task.prerequisite_task_keys:
        try:
            prereqs = json.loads(task.prerequisite_task_keys)
        except Exception:
            prereqs = []

    # Check dependencies if advancing to completed
    if new_status == "completed":
        unmet_keys = []
        for pkey in prereqs:
            ptask = tasks_by_key.get(pkey)
            if not ptask or ptask.status != "completed":
                unmet_keys.append(ptask.skill_name if ptask else pkey)

        if unmet_keys and not override_reason:
            raise ValueError(
                f"Cannot mark task '{task.skill_name}' as completed: Prerequisite tasks ({', '.join(unmet_keys)}) "
                f"are not yet completed. Provide an explicit override reason to bypass prerequisite dependencies."
            )
        if override_reason:
            task.override_reason = override_reason

        task.completed_at = get_naive_utc_now()
        task.completed_by = actor
    elif old_status == "completed" and new_status != "completed":
        task.completed_at = None
        task.completed_by = None

    task.status = new_status
    task.updated_at = get_naive_utc_now()

    # Create progress audit event
    event_notes = notes
    if override_reason:
        event_notes = f"Override Reason: {override_reason}. " + (notes or "")
    if not event_notes:
        event_notes = f"Status transitioned from {old_status} to {new_status}."

    event = TaskProgressEvent(
        task_id=task.id,
        from_status=old_status,
        to_status=new_status,
        evidence_id=task.evidence_id,
        notes=event_notes,
        actor=actor,
    )
    db.add(event)
    db.commit()
    db.refresh(task)

    unlocked = is_task_unlocked(prereqs, tasks_by_key)
    return format_task_dict(task, is_unlocked=unlocked)


def link_task_evidence(
    db: Session,
    mission_id: int,
    task_id: int,
    student_id: int,
    evidence_id: int,
    notes: str = "",
    actor: str = "student",
) -> dict[str, Any]:
    """Link an existing portfolio evidence item to a mission task."""
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    active_v = mission.active_version
    if not active_v:
        raise ValueError("Mission has no active version.")

    task = (
        db.query(MissionTask)
        .filter(
            MissionTask.id == task_id,
            MissionTask.version_id == active_v.id,
        )
        .first()
    )
    if not task:
        raise ValueError(f"Task ID {task_id} not found in active version.")

    evidence = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.id == evidence_id,
            EvidenceItem.student_id == student_id,
        )
        .first()
    )
    if not evidence:
        raise ValueError(f"Evidence item ID {evidence_id} not found for student.")

    task.evidence_id = evidence_id
    task.updated_at = get_naive_utc_now()

    event = TaskProgressEvent(
        task_id=task.id,
        from_status=task.status,
        to_status=task.status,
        evidence_id=evidence_id,
        notes=notes or f"Attached evidence #{evidence.id}: '{evidence.title}'.",
        actor=actor,
    )
    db.add(event)
    db.commit()
    db.refresh(task)

    tasks_by_key = {t.stable_key: t for t in active_v.tasks}
    prereqs = []
    if task.prerequisite_task_keys:
        try:
            prereqs = json.loads(task.prerequisite_task_keys)
        except Exception:
            prereqs = []
    unlocked = is_task_unlocked(prereqs, tasks_by_key)
    return format_task_dict(task, is_unlocked=unlocked)


def get_task_progress_history(
    db: Session,
    mission_id: int,
    task_id: int,
    student_id: int,
) -> list[dict[str, Any]]:
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    task = db.query(MissionTask).filter(MissionTask.id == task_id).first()
    if not task:
        raise ValueError(f"Task ID {task_id} not found.")

    events = (
        db.query(TaskProgressEvent)
        .filter(TaskProgressEvent.task_id == task_id)
        .order_by(TaskProgressEvent.created_at.desc())
        .all()
    )

    return [
        {
            "id": ev.id,
            "task_id": ev.task_id,
            "from_status": ev.from_status,
            "to_status": ev.to_status,
            "evidence_id": ev.evidence_id,
            "notes": ev.notes,
            "actor": ev.actor,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in events
    ]


def compute_proposal_diff(
    active_version: MissionVersion,
    proposed_plan: dict[str, Any],
) -> dict[str, Any]:
    """Compute structured delta between approved active version and proposed plan."""
    active_tasks = {t.stable_key: t for t in active_version.tasks}

    proposed_tasks: dict[str, dict[str, Any]] = {}
    for stage in proposed_plan.get("stages", []):
        stage_num = stage.get("stage_number", 1)
        for sk in stage.get("skills", []):
            stable_key = build_task_stable_key(sk["skill_id"], sk["target_level"])
            proposed_tasks[stable_key] = {
                "stable_key": stable_key,
                "skill_id": sk["skill_id"],
                "skill_name": sk["skill_name"],
                "category": sk["category"],
                "target_level": sk["target_level"],
                "stage_number": stage_num,
                "estimated_effort": sk.get("estimated_effort", {}),
            }

    added = []
    for k, p in proposed_tasks.items():
        if k not in active_tasks:
            added.append(p)

    removed = []
    for k, a in active_tasks.items():
        if k not in proposed_tasks:
            removed.append({
                "stable_key": a.stable_key,
                "skill_id": a.skill_id,
                "skill_name": a.skill_name,
                "target_level": a.target_level,
                "status": a.status,
            })

    retained = []
    rescheduled = []
    for k, a in active_tasks.items():
        if k in proposed_tasks:
            p = proposed_tasks[k]
            is_resched = (a.stage_number != p.get("stage_number"))
            item = {
                "stable_key": a.stable_key,
                "skill_id": a.skill_id,
                "skill_name": a.skill_name,
                "target_level": a.target_level,
                "preserved_status": a.status,
                "previous_stage": a.stage_number,
                "new_stage": p.get("stage_number"),
            }
            if is_resched:
                rescheduled.append(item)
            else:
                retained.append(item)

    proposed_effort = proposed_plan.get("total_estimated_effort", {})
    prop_min = proposed_effort.get("min_hours", 0)
    prop_max = proposed_effort.get("max_hours", 0)

    delta_min = prop_min - active_version.total_estimated_hours_min
    delta_max = prop_max - active_version.total_estimated_hours_max

    is_material = (
        len(added) > 0
        or len(removed) > 0
        or len(rescheduled) > 0
        or delta_min != 0
        or delta_max != 0
    )

    return {
        "is_material_difference": is_material,
        "added_tasks": added,
        "removed_tasks": removed,
        "rescheduled_tasks": rescheduled,
        "retained_tasks": retained,
        "effort_delta": {
            "min_hours": delta_min,
            "max_hours": delta_max,
        },
        "proposed_total_effort": {
            "min_hours": prop_min,
            "max_hours": prop_max,
        },
    }


def get_student_evidence(db: Session, student_id: int) -> list[dict[str, Any]]:
    """Return all portfolio evidence items for a student."""
    evidence_records = (
        db.query(EvidenceItem, Skill)
        .join(Skill, EvidenceItem.skill_id == Skill.id)
        .filter(EvidenceItem.student_id == student_id)
        .order_by(EvidenceItem.created_at.desc())
        .all()
    )
    return [
        {
            "id": ev.id,
            "skill_id": ev.skill_id,
            "skill_name": sk.name,
            "title": ev.title,
            "description": ev.description,
            "url": ev.url,
            "evidence_type": ev.evidence_type,
            "verified_by_staff": ev.verified_by_staff,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev, sk in evidence_records
    ]


def create_mission_change_proposal(
    db: Session,
    mission_id: int,
    student_id: int,
    proposal_title: str,
    rationale: str,
    proposed_plan: dict[str, Any],
    proposed_by: str = "system_planner",
) -> MissionChangeProposal:
    """Create a pending proposal representing a staged plan adjustment."""
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    active_v = mission.active_version
    if not active_v:
        raise ValueError("Cannot create change proposal: Mission has no active version.")

    diff = compute_proposal_diff(active_v, proposed_plan)

    # For agent planner, prevent duplicate pending proposals on the same active base version
    if proposed_by == "agent_planner":
        existing_pending = (
            db.query(MissionChangeProposal)
            .filter(
                MissionChangeProposal.mission_id == mission.id,
                MissionChangeProposal.status == "pending",
                MissionChangeProposal.base_version_number == active_v.version_number,
                MissionChangeProposal.proposed_by == "agent_planner",
            )
            .first()
        )
        if existing_pending:
            # Update existing pending proposal with updated diff, title, and plan
            existing_pending.proposal_title = proposal_title
            existing_pending.rationale = rationale
            existing_pending.diff_summary = json.dumps(diff)
            existing_pending.proposed_plan_payload = json.dumps(proposed_plan)
            db.commit()
            db.refresh(existing_pending)
            return existing_pending

    proposal = MissionChangeProposal(
        mission_id=mission.id,
        base_version_number=active_v.version_number,
        proposed_by=proposed_by,
        proposal_title=proposal_title,
        rationale=rationale,
        diff_summary=json.dumps(diff),
        proposed_plan_payload=json.dumps(proposed_plan),
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def get_mission_proposals(
    db: Session, mission_id: int, student_id: int
) -> list[dict[str, Any]]:
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    proposals = (
        db.query(MissionChangeProposal)
        .filter(MissionChangeProposal.mission_id == mission_id)
        .order_by(MissionChangeProposal.created_at.desc())
        .all()
    )

    results = []
    for p in proposals:
        diff = {}
        try:
            diff = json.loads(p.diff_summary)
        except Exception:
            diff = {}
        results.append({
            "id": p.id,
            "mission_id": p.mission_id,
            "base_version_number": p.base_version_number,
            "proposed_by": p.proposed_by,
            "proposal_title": p.proposal_title,
            "rationale": p.rationale,
            "diff_summary": diff,
            "status": p.status,
            "student_decision_notes": p.student_decision_notes,
            "decided_by": p.decided_by,
            "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return results


def get_mission_proposal_by_id(
    db: Session, mission_id: int, proposal_id: int, student_id: int
) -> Optional[dict[str, Any]]:
    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    p = (
        db.query(MissionChangeProposal)
        .filter(
            MissionChangeProposal.id == proposal_id,
            MissionChangeProposal.mission_id == mission_id,
        )
        .first()
    )
    if not p:
        return None

    diff = {}
    try:
        diff = json.loads(p.diff_summary)
    except Exception:
        diff = {}

    return {
        "id": p.id,
        "mission_id": p.mission_id,
        "base_version_number": p.base_version_number,
        "proposed_by": p.proposed_by,
        "proposal_title": p.proposal_title,
        "rationale": p.rationale,
        "diff_summary": diff,
        "status": p.status,
        "student_decision_notes": p.student_decision_notes,
        "decided_by": p.decided_by,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def approve_mission_proposal(
    db: Session,
    mission_id: int,
    proposal_id: int,
    student_id: int,
    decision_notes: Optional[str] = None,
) -> dict[str, Any]:
    """Explicitly approve a change proposal: creates new immutable MissionVersion while preserving work."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student ID {student_id} not found.")

    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    proposal = (
        db.query(MissionChangeProposal)
        .filter(
            MissionChangeProposal.id == proposal_id,
            MissionChangeProposal.mission_id == mission_id,
        )
        .first()
    )
    if not proposal:
        raise ValueError(f"Proposal ID {proposal_id} not found.")

    # Idempotent handling if already approved
    if proposal.status == "approved":
        return format_career_mission_dict(mission)

    if proposal.status == "rejected":
        raise ValueError("Cannot approve a proposal that has been rejected.")

    active_v = mission.active_version
    if not active_v:
        raise ValueError("Mission has no active version to revise.")

    # Detect stale proposal
    if proposal.base_version_number != active_v.version_number:
        raise ValueError(
            f"Stale proposal conflict: Proposal targets base version {proposal.base_version_number}, "
            f"but active mission is currently on version {active_v.version_number}. "
            f"Please generate a new proposal against the latest version."
        )

    # 1. Deactivate current active version
    active_v.is_active = False

    # 2. Parse proposed plan payload
    proposed_plan = json.loads(proposal.proposed_plan_payload)
    new_version_num = active_v.version_number + 1

    total_effort = proposed_plan.get("total_estimated_effort", {})
    min_hours = total_effort.get("min_hours", 0)
    max_hours = total_effort.get("max_hours", 0)

    # 3. Create new immutable MissionVersion
    new_version = MissionVersion(
        mission_id=mission.id,
        version_number=new_version_num,
        title=f"Version {new_version_num}.0 — {proposal.proposal_title}",
        rationale=proposal.rationale,
        source_schema_version="v1.0",
        plan_snapshot=proposal.proposed_plan_payload,
        is_active=True,
        created_by=proposal.proposed_by,
        approved_by=student.email,
        approved_at=get_naive_utc_now(),
        total_estimated_hours_min=min_hours,
        total_estimated_hours_max=max_hours,
    )
    db.add(new_version)
    db.flush()

    # Index old tasks by stable key for completed work preservation
    old_tasks_by_key = {t.stable_key: t for t in active_v.tasks}

    # Prerequisite graph for determining task-to-task dependency keys
    prereq_edges = db.query(SkillPrerequisite).all()
    prereq_graph: dict[int, list[int]] = {}
    for edge in prereq_edges:
        prereq_graph.setdefault(edge.skill_id, []).append(edge.prerequisite_id)

    all_plan_skill_keys: dict[int, str] = {}
    for stage in proposed_plan.get("stages", []):
        for sk in stage.get("skills", []):
            stable_key = build_task_stable_key(sk["skill_id"], sk["target_level"])
            all_plan_skill_keys[sk["skill_id"]] = stable_key

    # 4. Port and create new tasks
    for stage in proposed_plan.get("stages", []):
        stage_num = stage.get("stage_number", 1)
        stage_title = stage.get("stage_title", f"Stage {stage_num}")

        for sk in stage.get("skills", []):
            skill_id = sk["skill_id"]
            target_level = sk["target_level"]
            stable_key = build_task_stable_key(skill_id, target_level)

            task_prereq_keys = []
            for p_id in prereq_graph.get(skill_id, []):
                if p_id in all_plan_skill_keys and p_id != skill_id:
                    task_prereq_keys.append(all_plan_skill_keys[p_id])

            effort = sk.get("estimated_effort", {})
            criteria = generate_completion_criteria(sk["skill_name"], sk["category"], target_level)

            # Check if this task existed in previous version -> PRESERVE WORK
            old_task = old_tasks_by_key.get(stable_key)
            status = "not_started"
            completed_at = None
            completed_by = None
            override_reason = None
            evidence_id = None

            if old_task:
                status = old_task.status
                completed_at = old_task.completed_at
                completed_by = old_task.completed_by
                override_reason = old_task.override_reason
                evidence_id = old_task.evidence_id

            new_task = MissionTask(
                version_id=new_version.id,
                stable_key=stable_key,
                stage_number=stage_num,
                stage_title=stage_title,
                skill_id=skill_id,
                skill_name=sk["skill_name"],
                category=sk["category"],
                current_level=sk.get("current_level", 0),
                target_level=target_level,
                level_delta=sk.get("level_delta", 1),
                status=status,
                estimated_hours_min=effort.get("min_hours", 0),
                estimated_hours_max=effort.get("max_hours", 0),
                completion_criteria=criteria,
                rationale=sk.get("rationale", ""),
                prerequisite_task_keys=json.dumps(sorted(list(set(task_prereq_keys)))),
                evidence_id=evidence_id,
                completed_at=completed_at,
                completed_by=completed_by,
                override_reason=override_reason,
            )
            db.add(new_task)
            db.flush()

            # Record event
            event_note = (
                f"Task migrated to Version {new_version_num}.0 on approval of proposal #{proposal.id}."
            )
            if old_task and old_task.status == "completed":
                event_note += " Completed progress and evidence preserved."

            event = TaskProgressEvent(
                task_id=new_task.id,
                from_status=old_task.status if old_task else "none",
                to_status=status,
                evidence_id=evidence_id,
                notes=event_note,
                actor="student",
            )
            db.add(event)

    # 5. Mark Proposal as approved
    proposal.status = "approved"
    proposal.decided_by = student.email
    proposal.decided_at = get_naive_utc_now()
    proposal.student_decision_notes = decision_notes or ""

    mission.updated_at = get_naive_utc_now()

    db.commit()
    db.refresh(mission)
    return format_career_mission_dict(mission)


def reject_mission_proposal(
    db: Session,
    mission_id: int,
    proposal_id: int,
    student_id: int,
    decision_notes: Optional[str] = None,
) -> dict[str, Any]:
    """Reject a pending change proposal with student feedback notes."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError(f"Student ID {student_id} not found.")

    mission = get_career_mission_by_id(db, mission_id, student_id)
    if not mission:
        raise ValueError(f"Mission ID {mission_id} not found.")

    proposal = (
        db.query(MissionChangeProposal)
        .filter(
            MissionChangeProposal.id == proposal_id,
            MissionChangeProposal.mission_id == mission_id,
        )
        .first()
    )
    if not proposal:
        raise ValueError(f"Proposal ID {proposal_id} not found.")

    if proposal.status == "rejected":
        # Idempotent
        diff = {}
        try:
            diff = json.loads(proposal.diff_summary)
        except Exception:
            diff = {}
        return {
            "id": proposal.id,
            "mission_id": proposal.mission_id,
            "base_version_number": proposal.base_version_number,
            "proposed_by": proposal.proposed_by,
            "proposal_title": proposal.proposal_title,
            "rationale": proposal.rationale,
            "diff_summary": diff,
            "status": proposal.status,
            "student_decision_notes": proposal.student_decision_notes,
            "decided_by": proposal.decided_by,
            "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
            "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        }

    if proposal.status == "approved":
        raise ValueError("Cannot reject a proposal that has already been approved.")

    proposal.status = "rejected"
    proposal.decided_by = student.email
    proposal.decided_at = get_naive_utc_now()
    proposal.student_decision_notes = decision_notes or ""

    db.commit()
    db.refresh(proposal)

    diff = {}
    try:
        diff = json.loads(proposal.diff_summary)
    except Exception:
        diff = {}

    return {
        "id": proposal.id,
        "mission_id": proposal.mission_id,
        "base_version_number": proposal.base_version_number,
        "proposed_by": proposal.proposed_by,
        "proposal_title": proposal.proposal_title,
        "rationale": proposal.rationale,
        "diff_summary": diff,
        "status": proposal.status,
        "student_decision_notes": proposal.student_decision_notes,
        "decided_by": proposal.decided_by,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
    }

