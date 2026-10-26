from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------
# Phase 1: Matching Engine Schemas (Preserved)
# ---------------------------------------------------------

class MatchRequest(BaseModel):
    student_levels: list[int] = Field(min_length=1, max_length=256)
    required_levels: list[int] = Field(min_length=1, max_length=256)
    weights: list[int] = Field(min_length=1, max_length=256)
    mandatory: list[int] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def check_values(self):
        lengths = {len(self.student_levels), len(self.required_levels), len(self.weights), len(self.mandatory)}
        if len(lengths) != 1:
            raise ValueError("all four arrays must have equal length")
        if any(not 0 <= n <= 3 for n in self.student_levels):
            raise ValueError("student levels must be between 0 and 3")
        if any(not 1 <= n <= 3 for n in self.required_levels):
            raise ValueError("required levels must be between 1 and 3")
        if any(not 1 <= n <= 5 for n in self.weights):
            raise ValueError("weights must be between 1 and 5")
        if any(n not in (0, 1) for n in self.mandatory):
            raise ValueError("mandatory values must be 0 or 1")
        return self


class MatchResponse(BaseModel):
    earned_points: int
    max_points: int
    missing_mandatory: int
    mandatory_requirements_met: bool
    coverage_percent: float


# ---------------------------------------------------------
# Phase 3.1: Learning Path Engine & Catalog Schemas
# ---------------------------------------------------------
# Phase 3.1 & 3.2: Curriculum, Catalog & Profile Schemas (Canonical 0-3 Scale)
# ---------------------------------------------------------

class SkillItem(BaseModel):
    id: int
    name: str
    category: str
    max_level: int = 3
    description: str = ""
    prerequisites: list[int] = Field(default_factory=list)
    unlocked_skills: list[int] = Field(default_factory=list)


class RoleListItem(BaseModel):
    role_id: str
    title: str
    department: str
    location: str
    description: str
    requirements_count: int


class RoleRequirementItem(BaseModel):
    skill_id: int
    skill_name: str
    required_level: int = Field(ge=1, le=3)
    mandatory: bool = True
    role_context: str = ""


class RoleDetailResponse(BaseModel):
    role_id: str
    title: str
    department: str
    location: str
    description: str
    requirements: list[RoleRequirementItem]


class StudentSkillInput(BaseModel):
    skill_id: int = Field(gt=0, description="Valid skill ID in graph")
    level: int = Field(ge=0, le=3, description="Proficiency level (0=none, 1=basic, 2=intermediate, 3=advanced)")
    is_verified: bool = Field(default=False, description="Whether skill has been verified by external assessment")


class TargetSkillInput(BaseModel):
    skill_id: int = Field(gt=0, description="Valid skill ID in graph")
    required_level: int = Field(ge=1, le=3, description="Required target proficiency level (1 to 3)")


class LearningPathRequest(BaseModel):
    role_id: Optional[str] = Field(default=None, description="Identifier of target internship role from catalog")
    target_skills: Optional[list[TargetSkillInput]] = Field(default=None, description="Explicit target skills if not using role_id")
    student_skills: list[StudentSkillInput] = Field(default_factory=list, description="Current student skills")

    @model_validator(mode="after")
    def validate_request(self):
        if not self.role_id and not self.target_skills:
            raise ValueError("Must specify either a valid role_id or a list of target_skills.")

        # Check for duplicate student skill IDs
        seen_student_ids = set()
        for s in self.student_skills:
            if s.skill_id in seen_student_ids:
                raise ValueError(f"Duplicate student skill ID: {s.skill_id}")
            seen_student_ids.add(s.skill_id)

        # Check for duplicate target skill IDs if provided
        if self.target_skills:
            seen_target_ids = set()
            for t in self.target_skills:
                if t.skill_id in seen_target_ids:
                    raise ValueError(f"Duplicate target skill ID: {t.skill_id}")
                seen_target_ids.add(t.skill_id)

        return self


class EffortRangeItem(BaseModel):
    min_hours: int
    max_hours: int


class SkillUpgradeItem(BaseModel):
    skill_id: int
    skill_name: str
    category: str
    current_level: int
    target_level: int
    level_delta: int
    is_verified: bool
    verification_status: str
    estimated_effort: EffortRangeItem
    rationale: str


class LearningStageItem(BaseModel):
    stage_number: int
    stage_title: str
    stage_effort: EffortRangeItem
    skills: list[SkillUpgradeItem]


class AlgorithmTraceItem(BaseModel):
    graph_representation: str = "Directed Adjacency Lists via HashTable<int, DynamicArray<int>>"
    graph_node_count: int
    graph_edge_count: int
    prerequisite_closure_nodes_visited: int
    kahn_queue_enqueues: int
    kahn_queue_dequeues: int
    topo_stages_formed: int
    execution_time_microseconds: float


class LearningPathResponse(BaseModel):
    achievable: bool
    message: str
    target_skills: list[int]
    missing_skills: list[int]
    prerequisite_closure: list[int]
    total_estimated_effort: EffortRangeItem
    stages: list[LearningStageItem]
    algorithm_trace: Optional[AlgorithmTraceItem] = None


# ---------------------------------------------------------
# Phase 3.2: Student Profile & Evidence Persistence Schemas
# ---------------------------------------------------------

class StudentSkillRecord(BaseModel):
    skill_id: int
    skill_name: str
    category: str
    declared_level: int = Field(ge=0, le=3)
    verified_level: int = Field(ge=0, le=3)
    is_verified: bool
    verification_source: str = "unverified"
    updated_at: Optional[str] = None


class EvidenceItemResponse(BaseModel):
    id: int
    skill_id: int
    skill_name: str
    title: str
    description: str = ""
    url: Optional[str] = None
    evidence_type: str = "project"
    verified_by_staff: bool = False
    created_at: Optional[str] = None


class StudentProfileResponse(BaseModel):
    id: int
    name: str
    email: str
    target_role_id: Optional[str] = None
    weekly_hours: int
    is_demo: bool = True
    skills: list[StudentSkillRecord] = Field(default_factory=list)
    evidence: list[EvidenceItemResponse] = Field(default_factory=list)


class StudentSkillUpdateItem(BaseModel):
    skill_id: int
    declared_level: int = Field(ge=0, le=3)
    # Privileged verification fields: accepted for backwards compatibility with legacy client
    # payloads, but strictly ignored by the server boundary to prevent privilege escalation.
    verified_level: Optional[int] = Field(default=None, ge=0, le=3)
    is_verified: Optional[bool] = None


class StudentProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    target_role_id: Optional[str] = None
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=80)
    skills: Optional[list[StudentSkillUpdateItem]] = None


class EvidenceCreateRequest(BaseModel):
    skill_id: int
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    url: Optional[str] = None
    evidence_type: Optional[str] = "project"


# ---------------------------------------------------------
# Phase 3.3: Persistent Career Mission & Versioning Schemas
# ---------------------------------------------------------

class TaskProgressEventResponse(BaseModel):
    id: int
    task_id: int
    from_status: str
    to_status: str
    evidence_id: Optional[int] = None
    notes: str = ""
    actor: str = "student"
    created_at: Optional[str] = None


class MissionTaskResponse(BaseModel):
    id: int
    version_id: int
    stable_key: str
    stage_number: int
    stage_title: str
    skill_id: int
    skill_name: str
    category: str
    current_level: int
    target_level: int
    level_delta: int
    status: str
    is_unlocked: bool = True
    estimated_hours_min: int
    estimated_hours_max: int
    completion_criteria: str
    rationale: str
    prerequisite_task_keys: list[str] = Field(default_factory=list)
    evidence_id: Optional[int] = None
    completed_at: Optional[str] = None
    completed_by: Optional[str] = None
    override_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MissionStageResponse(BaseModel):
    stage_number: int
    stage_title: str
    total_tasks: int
    completed_tasks: int
    stage_hours_min: int
    stage_hours_max: int
    tasks: list[MissionTaskResponse] = Field(default_factory=list)


class MissionVersionSummaryResponse(BaseModel):
    id: int
    mission_id: int
    version_number: int
    title: str
    rationale: str
    is_active: bool
    created_by: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    total_estimated_hours_min: int
    total_estimated_hours_max: int
    total_tasks: int = 0
    created_at: Optional[str] = None


class MissionVersionDetailResponse(BaseModel):
    id: int
    mission_id: int
    version_number: int
    title: str
    rationale: str
    source_schema_version: str = "v1.0"
    is_active: bool
    created_by: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    total_estimated_hours_min: int
    total_estimated_hours_max: int
    total_tasks: int = 0
    completed_tasks: int = 0
    stages: list[MissionStageResponse] = Field(default_factory=list)
    tasks: list[MissionTaskResponse] = Field(default_factory=list)
    created_at: Optional[str] = None


class CareerMissionListItem(BaseModel):
    id: int
    student_id: int
    target_role_id: Optional[str] = None
    target_role_title: Optional[str] = None
    title: str
    status: str
    weekly_hours: int
    active_version_number: Optional[int] = None
    progress_percent: float = 0.0
    total_tasks: int = 0
    completed_tasks: int = 0
    created_at: Optional[str] = None


class CareerMissionResponse(BaseModel):
    id: int
    student_id: int
    target_role_id: Optional[str] = None
    target_role_title: Optional[str] = None
    title: str
    status: str
    weekly_hours: int
    active_version_number: Optional[int] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    progress_percent: float = 0.0
    estimated_remaining_hours_min: int = 0
    estimated_remaining_hours_max: int = 0
    active_version: Optional[MissionVersionDetailResponse] = None
    pending_proposals_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MissionCreateRequest(BaseModel):
    target_role_id: Optional[str] = None
    target_skills: Optional[list[TargetSkillInput]] = None
    title: Optional[str] = None
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=80)
    allow_replace_active: bool = False
    idempotency_key: Optional[str] = Field(default=None, max_length=128)



class TaskStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(not_started|in_progress|completed)$")
    override_reason: Optional[str] = None
    notes: Optional[str] = ""


class TaskLinkEvidenceRequest(BaseModel):
    evidence_id: int
    notes: Optional[str] = ""


class MissionChangeProposalResponse(BaseModel):
    id: int
    mission_id: int
    base_version_number: int
    proposed_by: str
    proposal_title: str
    rationale: str
    diff_summary: dict[str, Any]
    status: str
    student_decision_notes: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    created_at: Optional[str] = None


class ProposalCreateRequest(BaseModel):
    proposal_title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=5)
    target_role_id: Optional[str] = None
    notes: Optional[str] = ""


class ProposalDecisionRequest(BaseModel):
    decision_notes: Optional[str] = ""


# ---------------------------------------------------------
# Phase 3.4: Agentic Foundation Schemas
# ---------------------------------------------------------

class AgentEventCreateRequest(BaseModel):
    event_id: Optional[str] = None
    event_type: str = Field(
        pattern="^(internship_deadline_changed|student_skill_evidence_added|mission_progress_updated)$",
        description="Type of observed career environment event",
    )
    source: str = Field(min_length=2, max_length=100)
    source_timestamp: Optional[str] = None
    role_id: Optional[str] = None
    student_id: Optional[int] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    source_reliability: str = Field(
        default="verified_employer",
        pattern="^(verified_employer|trusted_internal|unverified_third_party|simulated_demo)$",
    )
    evidence_reference: Optional[str] = None
    is_simulated: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentEventResponse(BaseModel):
    id: int
    event_id: str
    event_type: str
    source: str
    source_timestamp: str
    received_at: str
    role_id: Optional[str] = None
    student_id: Optional[int] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    source_reliability: str
    evidence_reference: Optional[str] = None
    processing_status: str
    is_simulated: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AgentSimulateRequest(BaseModel):
    scenario: str = Field(
        pattern="^(deadline_earlier|deadline_extended|unrelated_role|evidence_added|untrusted_source|missing_deadline|zero_hours)$",
        description="Controlled demo scenario to simulate",
    )
    role_id: Optional[str] = None
    days_delta: Optional[int] = None
    custom_deadline: Optional[str] = None
    source_reliability: Optional[str] = None


class AgentDecisionResult(BaseModel):
    decision_category: str = Field(
        pattern="^(no_action|informational_notification|proposed_mission_adjustment|human_review_required)$"
    )
    explanation: str
    recommended_action: str
    confidence_score: float = Field(ge=0.0, le=1.0, default=1.0)
    tradeoffs: list[str] = Field(default_factory=list)
    suggested_proposal_title: Optional[str] = None
    suggested_proposal_rationale: Optional[str] = None


class AgentRunResponse(BaseModel):
    id: str
    event_id: str
    mission_id: Optional[int] = None
    student_id: int
    engine_used: str
    decision_category: str
    is_simulated: bool
    relevant_evidence: Optional[dict[str, Any]] = None
    tools_invoked: list[str] = Field(default_factory=list)
    tool_io_log: list[dict[str, Any]] = Field(default_factory=list)
    decision_explanation: str
    proposal_id: Optional[int] = None
    execution_time_ms: int = 0
    status: str
    error_message: Optional[str] = None
    created_at: str



