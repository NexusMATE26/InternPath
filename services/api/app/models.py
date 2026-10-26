from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base
from app.agent.clock import get_naive_utc_now


class Student(Base):
    """Represents a student user profile in InternPath.

    Phase 3.2 uses explicitly labeled local development mode.
    """
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    target_role_id = Column(
        String(100),
        ForeignKey("roles.role_id", ondelete="SET NULL"),
        nullable=True,
    )
    weekly_hours = Column(Integer, default=10, nullable=False)
    is_demo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=get_naive_utc_now, onupdate=get_naive_utc_now, nullable=False
    )

    # Relationships
    skills = relationship(
        "StudentSkill", back_populates="student", cascade="all, delete-orphan"
    )
    evidence = relationship(
        "EvidenceItem", back_populates="student", cascade="all, delete-orphan"
    )
    target_role = relationship("Role", foreign_keys=[target_role_id])
    missions = relationship(
        "CareerMission", back_populates="student", cascade="all, delete-orphan"
    )
    agent_events = relationship(
        "AgentEvent", back_populates="student", cascade="all, delete-orphan"
    )
    agent_runs = relationship(
        "AgentRun", back_populates="student", cascade="all, delete-orphan"
    )


class Skill(Base):
    """Canonical skill entity in the curriculum graph.

    PostgreSQL is the single source of truth for all competencies.
    """
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)  # Stable integer IDs (1..10)
    name = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    max_level = Column(Integer, default=3, nullable=False)  # Canonical 0-3 scale
    description = Column(Text, nullable=False, default="")
    is_demo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    # Relationships
    prerequisites = relationship(
        "SkillPrerequisite",
        foreign_keys="[SkillPrerequisite.skill_id]",
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    unlocked = relationship(
        "SkillPrerequisite",
        foreign_keys="[SkillPrerequisite.prerequisite_id]",
        back_populates="prerequisite",
        cascade="all, delete-orphan",
    )
    student_records = relationship(
        "StudentSkill", back_populates="skill", cascade="all, delete-orphan"
    )
    role_records = relationship(
        "RoleRequirement", back_populates="skill", cascade="all, delete-orphan"
    )


class StudentSkill(Base):
    """Student's declared and verified competence for a specific skill.

    Canonical proficiency scale:
      0 = None / Not declared
      1 = Basic (Foundations)
      2 = Intermediate (Working competence)
      3 = Advanced (Production-ready)
    """
    __tablename__ = "student_skills"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    declared_level = Column(Integer, nullable=False, default=0)
    verified_level = Column(Integer, nullable=False, default=0)
    is_verified = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime, default=get_naive_utc_now, onupdate=get_naive_utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("student_id", "skill_id", name="uq_student_skill"),
        CheckConstraint("declared_level >= 0 AND declared_level <= 3", name="ck_declared_level_range"),
        CheckConstraint("verified_level >= 0 AND verified_level <= 3", name="ck_verified_level_range"),
    )

    student = relationship("Student", back_populates="skills")
    skill = relationship("Skill", back_populates="student_records")


class EvidenceItem(Base):
    """Supporting portfolio item, project, or assessment record."""
    __tablename__ = "evidence_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    url = Column(String(500), nullable=True)
    evidence_type = Column(String(50), nullable=False, default="project")  # project, course, assessment, certification
    verified_by_staff = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    student = relationship("Student", back_populates="evidence")
    skill = relationship("Skill")


class Role(Base):
    """Target internship role offered in the catalogue."""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(150), nullable=False)
    department = Column(String(100), nullable=False)
    location = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    is_demo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    requirements = relationship(
        "RoleRequirement", back_populates="role", cascade="all, delete-orphan"
    )


class RoleRequirement(Base):
    """Competency requirements for an internship role."""
    __tablename__ = "role_requirements"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_id = Column(
        String(100), ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_level = Column(Integer, nullable=False, default=1)
    mandatory = Column(Boolean, default=True, nullable=False)
    role_context = Column(Text, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),
        CheckConstraint("required_level >= 1 AND required_level <= 3", name="ck_required_level_range"),
    )

    role = relationship("Role", back_populates="requirements")
    skill = relationship("Skill", back_populates="role_records")


class SkillPrerequisite(Base):
    """Directed prerequisite relationship between skills: prerequisite_id -> skill_id.

    Completing prerequisite_id is required before advancing in skill_id.
    """
    __tablename__ = "skill_prerequisites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prerequisite_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("skill_id", "prerequisite_id", name="uq_skill_prerequisite"),
        CheckConstraint("skill_id != prerequisite_id", name="ck_no_self_prerequisite"),
    )

    skill = relationship(
        "Skill", foreign_keys=[skill_id], back_populates="prerequisites"
    )
    prerequisite = relationship(
        "Skill", foreign_keys=[prerequisite_id], back_populates="unlocked"
    )


# ---------------------------------------------------------------------------
# Phase 3.3: Persistent Career Mission & Human-Approved Versioning System
# ---------------------------------------------------------------------------

class CareerMission(Base):
    """Actionable, persistent career mission generated from a learning path plan."""
    __tablename__ = "career_missions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_role_id = Column(
        String(100), ForeignKey("roles.role_id", ondelete="SET NULL"), nullable=True, index=True
    )
    title = Column(String(200), nullable=False)
    status = Column(String(50), nullable=False, default="active")  # active, completed, archived
    weekly_hours = Column(Integer, nullable=False, default=10)
    engine_metadata = Column(Text, nullable=False, default="{}")  # JSON: trace, node_count, edge_count
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=get_naive_utc_now, onupdate=get_naive_utc_now, nullable=False
    )

    student = relationship("Student", back_populates="missions")
    target_role = relationship("Role", foreign_keys=[target_role_id])
    versions = relationship(
        "MissionVersion",
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MissionVersion.version_number",
    )
    proposals = relationship(
        "MissionChangeProposal",
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MissionChangeProposal.created_at.desc()",
    )

    @property
    def active_version(self):
        for v in self.versions:
            if v.is_active:
                return v
        return self.versions[-1] if self.versions else None


class MissionVersion(Base):
    """Immutable version snapshot of a career mission's learning roadmap."""
    __tablename__ = "mission_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mission_id = Column(
        Integer, ForeignKey("career_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False, default="Initial Career Mission Plan")
    rationale = Column(
        Text, nullable=False, default="Generated from C++ LearningPathEngine topological plan."
    )
    source_schema_version = Column(String(50), nullable=False, default="v1.0")
    plan_snapshot = Column(Text, nullable=False, default="{}")  # JSON snapshot of full plan stages
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=False, default="system_planner")  # system_planner, agent_planner, student
    approved_by = Column(String(255), nullable=True)  # student email
    approved_at = Column(DateTime, nullable=True)
    total_estimated_hours_min = Column(Integer, nullable=False, default=0)
    total_estimated_hours_max = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "version_number", name="uq_mission_version"),
    )

    mission = relationship("CareerMission", back_populates="versions")
    tasks = relationship(
        "MissionTask",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="MissionTask.stage_number, MissionTask.id",
    )


class MissionTask(Base):
    """Individual milestone task within a mission version with a stable identity."""
    __tablename__ = "mission_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    version_id = Column(
        Integer, ForeignKey("mission_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stable_key = Column(String(100), nullable=False, index=True)  # Stable identity e.g. skill_4_lvl_2
    stage_number = Column(Integer, nullable=False, default=1)
    stage_title = Column(String(150), nullable=False)
    skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    current_level = Column(Integer, nullable=False, default=0)
    target_level = Column(Integer, nullable=False, default=1)
    level_delta = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="not_started")  # not_started, in_progress, completed
    estimated_hours_min = Column(Integer, nullable=False, default=0)
    estimated_hours_max = Column(Integer, nullable=False, default=0)
    completion_criteria = Column(Text, nullable=False, default="")
    rationale = Column(Text, nullable=False, default="")
    prerequisite_task_keys = Column(Text, nullable=False, default="[]")  # JSON list of stable_keys
    evidence_id = Column(
        Integer, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(String(255), nullable=True)
    override_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=get_naive_utc_now, onupdate=get_naive_utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed')",
            name="ck_task_status",
        ),
    )

    version = relationship("MissionVersion", back_populates="tasks")
    skill = relationship("Skill")
    evidence = relationship("EvidenceItem")
    progress_events = relationship(
        "TaskProgressEvent",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskProgressEvent.created_at.desc()",
    )


class TaskProgressEvent(Base):
    """Audit log tracking task status transitions and evidence attachments."""
    __tablename__ = "task_progress_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(
        Integer, ForeignKey("mission_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status = Column(String(50), nullable=False)
    to_status = Column(String(50), nullable=False)
    evidence_id = Column(
        Integer, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    notes = Column(Text, nullable=False, default="")
    actor = Column(String(100), nullable=False, default="student")
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    task = relationship("MissionTask", back_populates="progress_events")
    evidence = relationship("EvidenceItem")


class MissionChangeProposal(Base):
    """Staged plan alteration awaiting human approval by the student."""
    __tablename__ = "mission_change_proposals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mission_id = Column(
        Integer, ForeignKey("career_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_version_number = Column(Integer, nullable=False, default=1)
    proposed_by = Column(String(100), nullable=False, default="system_planner")  # agent_planner, system_planner
    proposal_title = Column(String(200), nullable=False)
    rationale = Column(Text, nullable=False)
    diff_summary = Column(Text, nullable=False)  # JSON: added_tasks, removed_tasks, modified_tasks, effort_delta
    proposed_plan_payload = Column(Text, nullable=False)  # JSON serialized full plan
    status = Column(String(50), nullable=False, default="pending")  # pending, approved, rejected
    student_decision_notes = Column(Text, nullable=True)
    decided_by = Column(String(255), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_proposal_status",
        ),
    )

    mission = relationship("CareerMission", back_populates="proposals")


# ---------------------------------------------------------------------------
# Phase 3.4: Agentic AI Foundation — Event Intake & Explainable Audit Log
# ---------------------------------------------------------------------------

class AgentEvent(Base):
    """Structured event contract for observable changes affecting student missions."""
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)  # internship_deadline_changed, student_skill_evidence_added, mission_progress_updated
    source = Column(String(100), nullable=False)  # employer_portal, mock_feed, simulated_demo, trusted_internal
    source_timestamp = Column(DateTime, nullable=False)
    received_at = Column(DateTime, default=get_naive_utc_now, nullable=False)
    role_id = Column(
        String(100), ForeignKey("roles.role_id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True, index=True
    )
    previous_value = Column(Text, nullable=True)  # JSON or ISO string representation
    new_value = Column(Text, nullable=True)       # JSON or ISO string representation
    source_reliability = Column(
        String(50), nullable=False, default="verified_employer"
    )  # verified_employer, trusted_internal, unverified_third_party, simulated_demo
    evidence_reference = Column(String(500), nullable=True)  # URL or internal record ID
    processing_status = Column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, processed, ignored, failed, requires_human_review
    is_simulated = Column(Boolean, nullable=False, default=False)
    payload = Column(Text, nullable=False, default="{}")  # Additional context as JSON
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending', 'processed', 'ignored', 'failed', 'requires_human_review')",
            name="ck_agent_event_processing_status",
        ),
        CheckConstraint(
            "source_reliability IN ('verified_employer', 'trusted_internal', 'unverified_third_party', 'simulated_demo')",
            name="ck_agent_event_source_reliability",
        ),
    )

    role = relationship("Role", foreign_keys=[role_id])
    student = relationship("Student", foreign_keys=[student_id])
    runs = relationship("AgentRun", back_populates="event", cascade="all, delete-orphan", order_by="AgentRun.created_at.desc()")


class AgentRun(Base):
    """Audit record of an AI agent execution, tools invoked, and resulting decision."""
    __tablename__ = "agent_runs"

    id = Column(String(64), primary_key=True, index=True)  # UUID string
    event_id = Column(
        String(64), ForeignKey("agent_events.event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id = Column(
        Integer, ForeignKey("career_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine_used = Column(String(100), nullable=False, default="deterministic_rules")  # deterministic_rules, gemini-1.5-flash, etc.
    decision_category = Column(
        String(50), nullable=False, index=True
    )  # no_action, informational_notification, proposed_mission_adjustment, human_review_required
    is_simulated = Column(Boolean, nullable=False, default=False)
    relevant_evidence = Column(Text, nullable=True)  # JSON summary of facts observed
    tools_invoked = Column(Text, nullable=False, default="[]")  # JSON list of tool names
    tool_io_log = Column(Text, nullable=False, default="[]")    # JSON list of sanitized {tool, input, output}
    decision_explanation = Column(Text, nullable=False)        # Transparent, human-readable justification
    proposal_id = Column(
        Integer, ForeignKey("mission_change_proposals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    execution_time_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="completed")  # completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "decision_category IN ('no_action', 'informational_notification', 'proposed_mission_adjustment', 'human_review_required')",
            name="ck_agent_run_decision_category",
        ),
        CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_agent_run_status",
        ),
    )

    event = relationship("AgentEvent", back_populates="runs")
    mission = relationship("CareerMission")
    student = relationship("Student")
    proposal = relationship("MissionChangeProposal")


class MissionIdempotencyRecord(Base):
    """Tracks mission creation idempotency keys and request fingerprints."""
    __tablename__ = "mission_idempotency_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload_fingerprint = Column(String(64), nullable=False)
    mission_id = Column(
        Integer, ForeignKey("career_missions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=get_naive_utc_now, nullable=False)

    student = relationship("Student")
    mission = relationship("CareerMission")



