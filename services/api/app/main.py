from typing import Optional, Any
import json
from fastapi import FastAPI, HTTPException, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .database import get_db
from . import crud, models
from .bridge import (
    EngineUnavailable,
    run_matching,
    run_learning_path,
    run_learning_path_with_graph,
)
from .fixtures import CURATED_SKILLS, CURATED_ROLES
from .agent.service import AgentService
from .schemas import (
    MatchRequest,
    MatchResponse,
    SkillItem,
    RoleListItem,
    RoleDetailResponse,
    RoleRequirementItem,
    TargetSkillInput,
    LearningPathRequest,
    LearningPathResponse,
    StudentProfileResponse,
    StudentProfileUpdateRequest,
    EvidenceCreateRequest,
    EvidenceItemResponse,
    CareerMissionResponse,
    CareerMissionListItem,
    MissionCreateRequest,
    MissionVersionSummaryResponse,
    MissionVersionDetailResponse,
    MissionTaskResponse,
    TaskStatusUpdateRequest,
    TaskLinkEvidenceRequest,
    TaskProgressEventResponse,
    MissionChangeProposalResponse,
    ProposalCreateRequest,
    ProposalDecisionRequest,
    AgentEventCreateRequest,
    AgentEventResponse,
    AgentSimulateRequest,
    AgentRunResponse,
    SimulatePlanVariantRequest,
    SimulatePlanVariantResponse,
    ComparePlanVariantsRequest,
    ComparePlanVariantsResponse,
    CheckPrerequisiteSafetyRequest,
    CheckPrerequisiteSafetyResponse,
    ToolDefinition,
)
from .agent.tools import AgentToolRegistry, ToolPermissionError



from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist
    from .database import engine, Base, SessionLocal
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Ensure deterministic default seed data is loaded
    from .seed import seed_database
    with SessionLocal() as db:
        seed_database(db, reset=False)
    yield


app = FastAPI(
    title="InternPath AI API",
    version="0.3.2",
    description="FastAPI service bridging web applications to custom C++20 DSA engines and persistent database.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)



# ---------------------------------------------------------
# Health & Phase 1 Match Endpoints
# ---------------------------------------------------------

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"
    return {
        "service": "internpath-api",
        "status": "ok",
        "version": "phase-3.2",
        "database": db_status,
    }


@app.post("/v1/demo/match", response_model=MatchResponse)
def demo_match(payload: MatchRequest):
    try:
        return run_matching(payload)
    except EngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


# ---------------------------------------------------------
# Phase 3.2: Curriculum & Catalog Database Endpoints
# ---------------------------------------------------------

@app.get("/v1/skills", response_model=list[SkillItem])
def get_skills(db: Session = Depends(get_db)):
    """Return all skills available in the persistent curriculum graph."""
    skills_data = crud.get_skills(db)
    if not skills_data:
        # Fallback to fixtures if DB not yet seeded
        return [SkillItem(**s) for s in CURATED_SKILLS]
    return [SkillItem(**s) for s in skills_data]


@app.get("/v1/roles", response_model=list[RoleListItem])
def get_roles(db: Session = Depends(get_db)):
    """Return summary list of available target internship roles."""
    roles_data = crud.get_roles(db)
    if not roles_data:
        results = []
        for r in CURATED_ROLES:
            results.append(
                RoleListItem(
                    role_id=r["role_id"],
                    title=r["title"],
                    department=r["department"],
                    location=r["location"],
                    description=r["description"],
                    requirements_count=len(r["requirements"]),
                )
            )
        return results
    return [RoleListItem(**r) for r in roles_data]


@app.get("/v1/roles/{role_id}/requirements", response_model=RoleDetailResponse)
def get_role_requirements(role_id: str, db: Session = Depends(get_db)):
    """Return detailed competency requirements for a given internship role."""
    role = crud.get_role_by_id(db, role_id)
    if role:
        req_items = [
            RoleRequirementItem(
                skill_id=req.skill_id,
                skill_name=req.skill.name if req.skill else f"Skill {req.skill_id}",
                required_level=req.required_level,
                mandatory=req.mandatory,
                role_context=req.role_context,
            )
            for req in role.requirements
        ]
        return RoleDetailResponse(
            role_id=role.role_id,
            title=role.title,
            department=role.department,
            location=role.location,
            description=role.description,
            requirements=req_items,
        )

    # Fallback to fixtures if DB not populated
    for r in CURATED_ROLES:
        if r["role_id"] == role_id:
            req_items = [RoleRequirementItem(**item) for item in r["requirements"]]
            return RoleDetailResponse(
                role_id=r["role_id"],
                title=r["title"],
                department=r["department"],
                location=r["location"],
                description=r["description"],
                requirements=req_items,
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Role '{role_id}' not found in internship catalogue.",
    )


# ---------------------------------------------------------
# Phase 3.2: Student Profile & Evidence Endpoints
# ---------------------------------------------------------

@app.get("/v1/profile", response_model=StudentProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    """Get the active development student profile."""
    dev_student = crud.get_or_create_dev_student(db)
    profile = crud.get_student_profile(db, dev_student.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found.",
        )
    return StudentProfileResponse(**profile)


@app.put("/v1/profile", response_model=StudentProfileResponse)
def update_profile(
    payload: StudentProfileUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update profile attributes and skills for the active development student."""
    dev_student = crud.get_or_create_dev_student(db)
    skills_dicts = None
    if payload.skills is not None:
        skills_dicts = [s.model_dump() for s in payload.skills]

    try:
        updated = crud.update_student_profile(
            db,
            student_id=dev_student.id,
            name=payload.name,
            target_role_id=payload.target_role_id,
            weekly_hours=payload.weekly_hours,
            skills_data=skills_dicts,
        )
        return StudentProfileResponse(**updated)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.get("/v1/evidence", response_model=list[EvidenceItemResponse])
def get_evidence(db: Session = Depends(get_db)):
    """Get all evidence records for the active development student."""
    dev_student = crud.get_or_create_dev_student(db)
    records = crud.get_evidence_for_student(db, dev_student.id)
    return [EvidenceItemResponse(**rec) for rec in records]


@app.post("/v1/evidence", response_model=EvidenceItemResponse, status_code=status.HTTP_201_CREATED)
def create_evidence(
    payload: EvidenceCreateRequest,
    db: Session = Depends(get_db),
):
    """Add a new evidence item for the active development student."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        item = crud.add_evidence(
            db,
            student_id=dev_student.id,
            skill_id=payload.skill_id,
            title=payload.title,
            description=payload.description or "",
            url=payload.url,
            evidence_type=payload.evidence_type or "project",
        )
        skill = crud.get_skill_by_id(db, payload.skill_id)
        return EvidenceItemResponse(
            id=item.id,
            skill_id=item.skill_id,
            skill_name=skill.name if skill else f"Skill {item.skill_id}",
            title=item.title,
            description=item.description,
            url=item.url,
            evidence_type=item.evidence_type,
            verified_by_staff=item.verified_by_staff,
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------
# Learning Path Generation (Database-driven C++20 engine)
# ---------------------------------------------------------

@app.post("/v1/learning-path/generate", response_model=LearningPathResponse)
def generate_learning_path(
    payload: LearningPathRequest,
    db: Session = Depends(get_db),
):
    """Generate a personalized, topologically staged learning plan via C++20 engine.

    Uses PostgreSQL/SQLite database as single source of truth for skills and DAG prerequisites.
    """
    db_skills = crud.get_skills(db)
    if not db_skills:
        db_skills = CURATED_SKILLS
        db_prereqs = [
            (1, 2), (1, 3), (2, 4), (9, 4), (3, 5),
            (4, 6), (5, 6), (7, 8), (8, 10),
        ]
    else:
        db_prereqs = crud.get_all_prerequisites(db)

    valid_skill_ids = {s["id"] for s in db_skills}

    # Validate target skills either from role_id or explicit target_skills
    target_inputs: list[TargetSkillInput] = []

    if payload.role_id:
        role = crud.get_role_by_id(db, payload.role_id)
        if role:
            for req in role.requirements:
                target_inputs.append(
                    TargetSkillInput(
                        skill_id=req.skill_id,
                        required_level=req.required_level,
                    )
                )
        else:
            # Fallback to curated roles
            matched_role = None
            for r in CURATED_ROLES:
                if r["role_id"] == payload.role_id:
                    matched_role = r
                    break
            if not matched_role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Role '{payload.role_id}' not found in internship catalogue.",
                )
            for req in matched_role["requirements"]:
                target_inputs.append(
                    TargetSkillInput(
                        skill_id=req["skill_id"],
                        required_level=req["required_level"],
                    )
                )
    elif payload.target_skills:
        target_inputs = payload.target_skills

    # Validate all target skill IDs exist in graph
    for t in target_inputs:
        if t.skill_id not in valid_skill_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Target skill ID {t.skill_id} does not exist in curriculum.",
            )

    # Validate student skill IDs exist in graph
    for s in payload.student_skills:
        if s.skill_id not in valid_skill_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Student skill ID {s.skill_id} does not exist in curriculum.",
            )

    try:
        # Dynamically stream graph from database over stdin
        plan = run_learning_path_with_graph(
            skills=db_skills,
            prerequisites=db_prereqs,
            targets=target_inputs,
            student=payload.student_skills,
        )
        return plan
    except EngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


# ---------------------------------------------------------
# Phase 3.3: Career Mission & Plan Versioning Endpoints
# ---------------------------------------------------------

@app.post("/v1/missions", response_model=CareerMissionResponse, status_code=status.HTTP_201_CREATED)
def create_mission(
    payload: MissionCreateRequest,
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """Generate and persist a new Career Mission with immutable Version 1.0 (with idempotency protection)."""
    dev_student = crud.get_or_create_dev_student(db)

    # Resolve target role and parameters
    target_role_id = payload.target_role_id or dev_student.target_role_id or "distributed-systems-intern"
    role = crud.get_role_by_id(db, target_role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target role '{target_role_id}' not found in catalogue.",
        )

    hours = payload.weekly_hours or dev_student.weekly_hours or 10
    idem_key = payload.idempotency_key or idempotency_key_header

    # Compute canonical fingerprint for this request
    fingerprint = crud.compute_mission_payload_fingerprint(
        student_id=dev_student.id,
        target_role_id=target_role_id,
        weekly_hours=hours,
        title=payload.title,
        allow_replace=payload.allow_replace_active,
    )

    # 1. Idempotency Check: if key exists, verify fingerprint
    if idem_key:
        existing_record = crud.get_mission_idempotency_record(db, idem_key)
        if existing_record:
            if existing_record.payload_fingerprint == fingerprint:
                # Same key and same payload: return original mission without creating duplicate
                existing_mission = crud.get_career_mission_by_id(db, existing_record.mission_id, dev_student.id)
                if existing_mission:
                    mission_dict = crud.format_career_mission_dict(existing_mission)
                    return CareerMissionResponse(**mission_dict)
            else:
                # Same key with different payload: reject with HTTP 409
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Idempotency conflict: Key '{idem_key}' was already processed with a different payload. "
                        "Reusing an idempotency key with modified parameters is not permitted."
                    ),
                )

    # Collect student skills
    profile = crud.get_student_profile(db, dev_student.id)
    student_skills = []
    if profile:
        for sk in profile["skills"]:
            if sk["declared_level"] > 0:
                student_skills.append({
                    "skill_id": sk["skill_id"],
                    "level": sk["declared_level"],
                    "is_verified": sk["is_verified"],
                })

    # Prepare curriculum graph and target inputs
    db_skills = crud.get_skills(db)
    db_prereqs = crud.get_all_prerequisites(db)
    target_inputs = [
        TargetSkillInput(skill_id=req.skill_id, required_level=req.required_level)
        for req in role.requirements
    ]

    try:
        plan_obj = run_learning_path_with_graph(
            skills=db_skills,
            prerequisites=db_prereqs,
            targets=target_inputs,
            student=student_skills,
        )
        plan_data = plan_obj.model_dump()
    except EngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        mission = crud.create_career_mission_from_plan(
            db,
            student_id=dev_student.id,
            plan_data=plan_data,
            target_role_id=target_role_id,
            title=payload.title,
            weekly_hours=hours,
            allow_replace_active=payload.allow_replace_active,
            idempotency_key=idem_key,
            payload_fingerprint=fingerprint,
        )
        mission_dict = crud.format_career_mission_dict(mission)
        return CareerMissionResponse(**mission_dict)
    except IntegrityError as exc:
        db.rollback()
        if idem_key:
            existing_record = crud.get_mission_idempotency_record(db, idem_key)
            if existing_record and existing_record.payload_fingerprint == fingerprint:
                existing_mission = crud.get_career_mission_by_id(db, existing_record.mission_id, dev_student.id)
                if existing_mission:
                    mission_dict = crud.format_career_mission_dict(existing_mission)
                    return CareerMissionResponse(**mission_dict)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict occurred during concurrent mission creation.",
        ) from exc
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
        ) from exc


@app.get("/v1/missions", response_model=list[CareerMissionListItem])
def list_missions(db: Session = Depends(get_db)):
    """List all Career Missions for the active development student."""
    dev_student = crud.get_or_create_dev_student(db)
    missions_list = crud.get_career_missions_for_student(db, dev_student.id)
    return [CareerMissionListItem(**m) for m in missions_list]


@app.get("/v1/missions/active", response_model=CareerMissionResponse)
def get_active_mission(db: Session = Depends(get_db)):
    """Retrieve the currently active Career Mission with full roadmap and progress."""
    dev_student = crud.get_or_create_dev_student(db)
    active_m = crud.get_active_career_mission(db, dev_student.id)
    if not active_m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Career Mission found for this student. Create a mission first.",
        )
    return CareerMissionResponse(**crud.format_career_mission_dict(active_m))


@app.get("/v1/missions/{mission_id}", response_model=CareerMissionResponse)
def get_mission_by_id(mission_id: int, db: Session = Depends(get_db)):
    """Retrieve details and roadmap for a specific Career Mission."""
    dev_student = crud.get_or_create_dev_student(db)
    mission = crud.get_career_mission_by_id(db, mission_id, dev_student.id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Career Mission #{mission_id} not found.",
        )
    return CareerMissionResponse(**crud.format_career_mission_dict(mission))


@app.get("/v1/missions/{mission_id}/versions", response_model=list[MissionVersionSummaryResponse])
def get_mission_versions(mission_id: int, db: Session = Depends(get_db)):
    """Retrieve all historical and active versions for a mission."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        versions = crud.get_mission_versions(db, mission_id, dev_student.id)
        return [MissionVersionSummaryResponse(**v) for v in versions]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@app.get(
    "/v1/missions/{mission_id}/versions/{version_number}",
    response_model=MissionVersionDetailResponse,
)
def get_mission_version_detail(
    mission_id: int, version_number: int, db: Session = Depends(get_db)
):
    """Retrieve full roadmap snapshot of an immutable mission version."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        v_data = crud.get_mission_version_detail(db, mission_id, version_number, dev_student.id)
        if not v_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} for Mission #{mission_id} not found.",
            )
        return MissionVersionDetailResponse(**v_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@app.patch("/v1/missions/{mission_id}/tasks/{task_id}/status", response_model=MissionTaskResponse)
def update_task_status(
    mission_id: int,
    task_id: int,
    payload: TaskStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update task status with prerequisite dependency validation and audit logging."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        updated_task = crud.update_mission_task_status(
            db,
            mission_id=mission_id,
            task_id=task_id,
            student_id=dev_student.id,
            new_status=payload.status,
            override_reason=payload.override_reason,
            notes=payload.notes or "",
            actor="student",
        )
        return MissionTaskResponse(**updated_task)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from exc


@app.post("/v1/missions/{mission_id}/tasks/{task_id}/evidence", response_model=MissionTaskResponse)
def link_evidence_to_task(
    mission_id: int,
    task_id: int,
    payload: TaskLinkEvidenceRequest,
    db: Session = Depends(get_db),
):
    """Link a student evidence item to a mission task."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        updated_task = crud.link_task_evidence(
            db,
            mission_id=mission_id,
            task_id=task_id,
            student_id=dev_student.id,
            evidence_id=payload.evidence_id,
            notes=payload.notes or "",
            actor="student",
        )
        return MissionTaskResponse(**updated_task)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from exc


@app.get(
    "/v1/missions/{mission_id}/tasks/{task_id}/history",
    response_model=list[TaskProgressEventResponse],
)
def get_task_history(mission_id: int, task_id: int, db: Session = Depends(get_db)):
    """Retrieve full audit log history for a specific mission task."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        events = crud.get_task_progress_history(
            db,
            mission_id=mission_id,
            task_id=task_id,
            student_id=dev_student.id,
        )
        return [TaskProgressEventResponse(**ev) for ev in events]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.post(
    "/v1/missions/{mission_id}/proposals",
    response_model=MissionChangeProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_change_proposal(
    mission_id: int,
    payload: ProposalCreateRequest,
    db: Session = Depends(get_db),
):
    """Generate a structured plan-change proposal comparing the active version with a proposed plan."""
    dev_student = crud.get_or_create_dev_student(db)
    mission = crud.get_career_mission_by_id(db, mission_id, dev_student.id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Career Mission #{mission_id} not found.",
        )

    # Determine role for replanning
    target_role_id = payload.target_role_id or mission.target_role_id or "distributed-systems-intern"
    role = crud.get_role_by_id(db, target_role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target role '{target_role_id}' not found.",
        )

    # Run C++ engine to generate the proposed plan
    profile = crud.get_student_profile(db, dev_student.id)
    student_skills = []
    if profile:
        for sk in profile["skills"]:
            if sk["declared_level"] > 0:
                student_skills.append({
                    "skill_id": sk["skill_id"],
                    "level": sk["declared_level"],
                    "is_verified": sk["is_verified"],
                })

    db_skills = crud.get_skills(db)
    db_prereqs = crud.get_all_prerequisites(db)
    target_inputs = [
        TargetSkillInput(skill_id=req.skill_id, required_level=req.required_level)
        for req in role.requirements
    ]

    try:
        plan_obj = run_learning_path_with_graph(
            skills=db_skills,
            prerequisites=db_prereqs,
            targets=target_inputs,
            student=student_skills,
        )
        proposed_plan = plan_obj.model_dump()
    except EngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        proposal = crud.create_mission_change_proposal(
            db,
            mission_id=mission_id,
            student_id=dev_student.id,
            proposal_title=payload.proposal_title,
            rationale=payload.rationale,
            proposed_plan=proposed_plan,
            proposed_by="system_planner",
        )
        p_dict = crud.get_mission_proposal_by_id(db, mission_id, proposal.id, dev_student.id)
        return MissionChangeProposalResponse(**p_dict)  # type: ignore
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@app.get(
    "/v1/missions/{mission_id}/proposals",
    response_model=list[MissionChangeProposalResponse],
)
def get_mission_proposals(mission_id: int, db: Session = Depends(get_db)):
    """Retrieve all pending, approved, and rejected change proposals for a mission."""
    dev_student = crud.get_or_create_dev_student(db)
    try:
        proposals = crud.get_mission_proposals(db, mission_id, dev_student.id)
        return [MissionChangeProposalResponse(**p) for p in proposals]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get(
    "/v1/missions/{mission_id}/proposals/{proposal_id}",
    response_model=MissionChangeProposalResponse,
)
def get_mission_proposal(
    mission_id: int, proposal_id: int, db: Session = Depends(get_db)
):
    """Retrieve detailed proposal diff and proposed plan."""
    dev_student = crud.get_or_create_dev_student(db)
    p = crud.get_mission_proposal_by_id(db, mission_id, proposal_id, dev_student.id)
    if not p:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal #{proposal_id} not found on Mission #{mission_id}.",
        )
    return MissionChangeProposalResponse(**p)


@app.post(
    "/v1/missions/{mission_id}/proposals/{proposal_id}/approve",
    response_model=CareerMissionResponse,
)
def approve_proposal(
    mission_id: int,
    proposal_id: int,
    payload: Optional[ProposalDecisionRequest] = None,
    db: Session = Depends(get_db),
):
    """Human approval of staged plan change: creates new immutable MissionVersion."""
    dev_student = crud.get_or_create_dev_student(db)
    notes = payload.decision_notes if payload else None
    try:
        updated_mission = crud.approve_mission_proposal(
            db,
            mission_id=mission_id,
            proposal_id=proposal_id,
            student_id=dev_student.id,
            decision_notes=notes,
        )
        return CareerMissionResponse(**updated_mission)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        if "stale proposal" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from exc


@app.post(
    "/v1/missions/{mission_id}/proposals/{proposal_id}/reject",
    response_model=MissionChangeProposalResponse,
)
def reject_proposal(
    mission_id: int,
    proposal_id: int,
    payload: Optional[ProposalDecisionRequest] = None,
    db: Session = Depends(get_db),
):
    """Human rejection of staged plan change."""
    dev_student = crud.get_or_create_dev_student(db)
    notes = payload.decision_notes if payload else None
    try:
        rejected = crud.reject_mission_proposal(
            db,
            mission_id=mission_id,
            proposal_id=proposal_id,
            student_id=dev_student.id,
            decision_notes=notes,
        )
        return MissionChangeProposalResponse(**rejected)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from exc


# ---------------------------------------------------------------------------
# Phase 3.4: Agentic AI Foundation Endpoints
# ---------------------------------------------------------------------------

def format_agent_event_dict(ev: models.AgentEvent) -> dict[str, Any]:
    payload = {}
    if ev.payload:
        try:
            payload = json.loads(ev.payload)
        except Exception:
            payload = {}
    return {
        "id": ev.id,
        "event_id": ev.event_id,
        "event_type": ev.event_type,
        "source": ev.source,
        "source_timestamp": ev.source_timestamp.isoformat() if ev.source_timestamp else "",
        "received_at": ev.received_at.isoformat() if ev.received_at else "",
        "role_id": ev.role_id,
        "student_id": ev.student_id,
        "previous_value": ev.previous_value,
        "new_value": ev.new_value,
        "source_reliability": ev.source_reliability,
        "evidence_reference": ev.evidence_reference,
        "processing_status": ev.processing_status,
        "is_simulated": ev.is_simulated,
        "payload": payload,
        "created_at": ev.created_at.isoformat() if ev.created_at else "",
    }


def format_agent_run_dict(run: models.AgentRun) -> dict[str, Any]:
    rel_ev = None
    if run.relevant_evidence:
        try:
            rel_ev = json.loads(run.relevant_evidence)
        except Exception:
            rel_ev = {"raw": run.relevant_evidence}
    tools = []
    if run.tools_invoked:
        try:
            tools = json.loads(run.tools_invoked)
        except Exception:
            tools = []
    io_log = []
    if run.tool_io_log:
        try:
            io_log = json.loads(run.tool_io_log)
        except Exception:
            io_log = []

    return {
        "id": run.id,
        "event_id": run.event_id,
        "mission_id": run.mission_id,
        "student_id": run.student_id,
        "engine_used": run.engine_used,
        "decision_category": run.decision_category,
        "is_simulated": run.is_simulated,
        "relevant_evidence": rel_ev,
        "tools_invoked": tools,
        "tool_io_log": io_log,
        "decision_explanation": run.decision_explanation,
        "proposal_id": run.proposal_id,
        "execution_time_ms": run.execution_time_ms,
        "status": run.status,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else "",
    }


@app.post("/v1/agent/events", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def ingest_agent_event(
    payload: AgentEventCreateRequest,
    db: Session = Depends(get_db),
):
    """Ingest an external or internal career event and execute agent reasoning workflow."""
    dev_student = crud.get_or_create_dev_student(db)
    agent_svc = AgentService(db, dev_student.id)
    try:
        run = agent_svc.process_event(payload)
        return AgentRunResponse(**format_agent_run_dict(run))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Agent workflow execution error: {exc}",
        ) from exc


@app.post("/v1/agent/events/simulate", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def simulate_agent_event(
    payload: AgentSimulateRequest,
    db: Session = Depends(get_db),
):
    """Trigger a controlled demo simulation event for presenter evaluation."""
    dev_student = crud.get_or_create_dev_student(db)
    agent_svc = AgentService(db, dev_student.id)
    try:
        run = agent_svc.simulate_demo_event(payload)
        return AgentRunResponse(**format_agent_run_dict(run))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Simulation error: {exc}",
        ) from exc


@app.get("/v1/agent/events", response_model=list[AgentEventResponse])
def list_agent_events(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve history of observed environment and simulation events."""
    events = (
        db.query(models.AgentEvent)
        .order_by(models.AgentEvent.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [AgentEventResponse(**format_agent_event_dict(ev)) for ev in events]


@app.get("/v1/agent/runs", response_model=list[AgentRunResponse])
def list_agent_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve audit history of agent decision runs and tool executions."""
    runs = (
        db.query(models.AgentRun)
        .order_by(models.AgentRun.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [AgentRunResponse(**format_agent_run_dict(r)) for r in runs]


@app.get("/v1/agent/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run_by_id(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve a single agent run audit record with full tool I/O trace."""
    run = db.query(models.AgentRun).filter(models.AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run '{run_id}' not found.",
        )
    return AgentRunResponse(**format_agent_run_dict(run))


# ---------------------------------------------------------------------------
# Phase R2.1: Agent Tool Registry & Counterfactual Plan Simulation Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/v1/agent/tools/simulate-plan-variant",
    response_model=SimulatePlanVariantResponse,
    status_code=status.HTTP_200_OK,
)
def simulate_plan_variant_endpoint(
    payload: SimulatePlanVariantRequest,
    db: Session = Depends(get_db),
):
    """Simulate counterfactual adjustment to active Career Mission without database mutation."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    try:
        result = registry.execute_tool(
            "simulate_plan_variant",
            variant_type=payload.variant_type,
            weekly_hours=payload.weekly_hours,
            target_date=payload.target_date,
            defer_optional_skills=payload.defer_optional_skills,
            temporary_availability_overrides=payload.temporary_availability_overrides,
            rationale=payload.rationale,
            mission_id=payload.mission_id,
        )
        return SimulatePlanVariantResponse(**result)
    except ToolPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation error: {exc}",
        ) from exc


@app.post(
    "/v1/agent/tools/compare-plan-variants",
    response_model=ComparePlanVariantsResponse,
    status_code=status.HTTP_200_OK,
)
def compare_plan_variants_endpoint(
    payload: ComparePlanVariantsRequest,
    db: Session = Depends(get_db),
):
    """Compare multiple simulated plan variants across feasibility, runway, and trade-offs."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    try:
        result = registry.execute_tool(
            "compare_plan_variants",
            simulations=payload.simulations,
        )
        return ComparePlanVariantsResponse(**result)
    except ToolPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.post(
    "/v1/agent/tools/check-prerequisite-safety",
    response_model=CheckPrerequisiteSafetyResponse,
    status_code=status.HTTP_200_OK,
)
def check_prerequisite_safety_endpoint(
    payload: CheckPrerequisiteSafetyRequest,
    db: Session = Depends(get_db),
):
    """Validate whether target skills and completed skills form a cycle-free DAG."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    try:
        result = registry.execute_tool(
            "check_prerequisite_safety",
            target_skills=payload.target_skills,
            completed_skills=payload.completed_skills,
        )
        return CheckPrerequisiteSafetyResponse(**result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.get(
    "/v1/agent/tools",
    response_model=list[ToolDefinition],
    status_code=status.HTTP_200_OK,
)
def list_agent_tool_definitions(
    db: Session = Depends(get_db),
):
    """List provider-neutral tool definitions and parameter schemas for LLM tool calling."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    return registry.get_tool_definitions()


@app.get(
    "/v1/agent/tools/gemini",
    status_code=status.HTTP_200_OK,
)
def export_gemini_tools_endpoint(
    db: Session = Depends(get_db),
):
    """Export tool declarations formatted for Google Gemini function calling API."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    return registry.export_gemini_tools()


@app.get(
    "/v1/agent/tools/openai",
    status_code=status.HTTP_200_OK,
)
def export_openai_tools_endpoint(
    db: Session = Depends(get_db),
):
    """Export tool declarations formatted for OpenAI function calling API."""
    dev_student = crud.get_or_create_dev_student(db)
    registry = AgentToolRegistry(db, dev_student.id)
    return registry.export_openai_tools()



