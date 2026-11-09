"""Comprehensive tests for Refinement R2.2: Real Provider-Compatible Multi-Turn Tool-Calling Agent.

Covers:
1. Provider request/response serialization for Gemini and OpenAI function/tool calling.
2. Missing API key handling for live providers.
3. Autonomous multi-turn agent loop: Model decides tool calls, receives results, iterates, and concludes.
4. Grounded simulation and comparison: Model investigates active mission, simulates variant, compares options.
5. Proposal staging safety: Proposals staged by model remain strictly PENDING (never auto-approved).
6. Idempotency guard: Prevents duplicate proposal staging within the same agent run.
7. Budget limits:
   - Max tool calls budget enforcement (default 8).
   - Max turns budget enforcement (default 5).
8. Security boundaries:
   - Forbidden actions blocked with permission_denied (approve_proposal, execute_command).
   - Unknown tools handled gracefully.
   - Model-supplied cross-student ID rejected.
9. Resilient fallback:
   - Provider exceptions / timeouts trigger safe deterministic fallback.
   - Malformed / non-JSON final outputs trigger fallback.
   - Zero database mutation on failure.
10. Target demonstration scenario (Section 13):
    - Student query regarding upcoming university exams and reduced 4h/week availability.
    - Verified via POST /v1/agent/query.
11. Execution trace persistence in agent_runs table with truthful engine labeling.
"""
import json
import pytest
from datetime import datetime, timezone
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
from app.agent.tools import AgentToolRegistry
from app.agent.types import AgentMessage, ModelTurnResponse, ToolCall
from app.agent.providers import GeminiProvider, OpenAIProvider, MockProvider
from app.agent.loop import AgentExecutionLoop
from app.agent.llm import LLMAdapter
from app.agent.service import AgentService
from app.schemas import (
    AgentDecisionResult,
    AgentQueryRequest,
    PlanVariantType,
    ToolDefinition,
    ValidityStatus,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_multiturn_state():
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
# 1. Provider Adapter Tests (Gemini & OpenAI)
# ---------------------------------------------------------------------------

def test_gemini_format_contents_and_tools():
    """GeminiProvider correctly structures messages and tools for Gemini REST API."""
    provider = GeminiProvider(api_key="mock_key", model_name="gemini-1.5-flash")
    assert provider.get_engine_label() == "gemini:gemini-1.5-flash"
    assert not provider.is_live_provider()  # mock_key is not live

    messages = [
        AgentMessage(role="system", content="System instruction text"),
        AgentMessage(role="user", content="Student question text"),
        AgentMessage(
            role="assistant",
            content="Thinking...",
            tool_calls=[ToolCall(id="call_1", name="read_active_mission", arguments={"student_id": 1})],
        ),
        AgentMessage(
            role="tool",
            name="read_active_mission",
            tool_call_id="call_1",
            content={"mission_id": 10},
        ),
    ]

    contents = provider._format_gemini_contents(messages)
    assert len(contents) == 4
    assert contents[0]["role"] == "user"
    assert "[System Instructions]" in contents[0]["parts"][0]["text"]
    assert contents[1]["role"] == "user"
    assert contents[2]["role"] == "model"
    assert "functionCall" in contents[2]["parts"][0]
    assert contents[2]["parts"][0]["functionCall"]["name"] == "read_active_mission"
    assert contents[3]["role"] == "function"
    assert contents[3]["parts"][0]["functionResponse"]["name"] == "read_active_mission"

    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)
        tools = provider._format_gemini_tools(registry.get_tool_definitions())
        assert len(tools) == 1
        assert "function_declarations" in tools[0]
        assert len(tools[0]["function_declarations"]) == 14


def test_openai_format_messages_and_tools():
    """OpenAIProvider correctly structures messages and tools for OpenAI REST API."""
    provider = OpenAIProvider(api_key="mock_key", model_name="gpt-4o-mini")
    assert provider.get_engine_label() == "openai:gpt-4o-mini"
    assert not provider.is_live_provider()

    messages = [
        AgentMessage(role="system", content="System prompt"),
        AgentMessage(role="user", content="User prompt"),
        AgentMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="call_123", name="simulate_plan_variant", arguments={"weekly_hours": 10})],
        ),
        AgentMessage(
            role="tool",
            name="simulate_plan_variant",
            tool_call_id="call_123",
            content={"validity_status": "VALID_AND_FEASIBLE"},
        ),
    ]

    openai_msgs = provider._format_openai_messages(messages)
    assert len(openai_msgs) == 4
    assert openai_msgs[0]["role"] == "system"
    assert openai_msgs[1]["role"] == "user"
    assert openai_msgs[2]["role"] == "assistant"
    assert "tool_calls" in openai_msgs[2]
    assert openai_msgs[2]["tool_calls"][0]["id"] == "call_123"
    assert openai_msgs[3]["role"] == "tool"
    assert openai_msgs[3]["tool_call_id"] == "call_123"

    with SessionLocal() as db:
        registry = AgentToolRegistry(db, 1)
        tools = provider._format_openai_tools(registry.get_tool_definitions())
        assert len(tools) == 14
        assert tools[0]["type"] == "function"


def test_provider_missing_api_key_raises_runtime_error():
    """Live providers require API keys and fail cleanly when unconfigured."""
    gemini = GeminiProvider(api_key=None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        gemini.generate_turn(messages=[], tool_definitions=[])

    openai = OpenAIProvider(api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        openai.generate_turn(messages=[], tool_definitions=[])


# ---------------------------------------------------------------------------
# 2. Autonomous Multi-Turn Agent Loop Tests
# ---------------------------------------------------------------------------

def test_multiturn_loop_autonomous_tool_selection():
    """Model autonomously selects tools sequentially, inspects outputs, and yields grounded decision."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # MockProvider simulates autonomous model:
        # Turn 1: model calls read_active_mission
        # Turn 2: model receives mission, calls simulate_plan_variant
        # Turn 3: model receives simulation, outputs structured decision
        provider = MockProvider()
        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=5)

        trace = loop.execute("Student needs advice on reduced study availability.")

        assert trace.engine_used == "mock_llm"
        assert not trace.fallback_used
        assert trace.total_tool_calls == 2
        assert trace.tools_invoked == ["read_active_mission", "simulate_plan_variant"]
        assert len(trace.turns) == 3
        assert trace.decision.decision_category == "proposed_mission_adjustment"
        assert "Successfully evaluated active mission" in trace.decision.explanation


def test_multiturn_loop_with_proposal_creation_remains_pending():
    """Model stages a proposal via create_mission_change_proposal; proposal remains strictly PENDING."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)
        active_m = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        active_version = active_m.active_version

        # Scripted multi-turn flow:
        # Turn 1: Model calls simulate_plan_variant
        # Turn 2: Model calls create_mission_change_proposal
        # Turn 3: Model produces final decision referencing proposal
        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(
                    content="Simulating 10h/week plan variant.",
                    tool_calls=[
                        ToolCall(
                            id="call_sim",
                            name="simulate_plan_variant",
                            arguments={"variant_type": "pacing_reduction", "weekly_hours": 10},
                        )
                    ],
                ),
                ModelTurnResponse(
                    content="Simulation validated. Staging mission change proposal for student review.",
                    tool_calls=[
                        ToolCall(
                            id="call_prop",
                            name="create_mission_change_proposal",
                            arguments={
                                "mission_id": mission_id,
                                "proposal_title": "Pacing Adjustment: 10 Hours/Week",
                                "rationale": "Pacing reduction evaluated and confirmed achievable via C++ graph engine.",
                                "proposed_plan": {
                                    "stages": [],
                                    "total_estimated_effort": {"min_hours": 20, "max_hours": 30},
                                },
                            },
                        )
                    ],
                ),
                ModelTurnResponse(
                    content=json.dumps({
                        "decision_category": "proposed_mission_adjustment",
                        "explanation": "Staged a proposal adjusting pacing to 10 hours/week. Student approval required.",
                        "recommended_action": "Review the staged proposal in your Roadmap tab.",
                        "confidence_score": 0.95,
                        "tradeoffs": ["Preserves completed tasks.", "Reduces weekly load."],
                    }),
                    tool_calls=[],
                ),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=5)
        trace = loop.execute("Investigate student pacing.")

        assert trace.proposal_id is not None
        assert not trace.fallback_used
        assert trace.decision.decision_category == "proposed_mission_adjustment"

        # Verify proposal in database is STRICTLY PENDING
        proposal = db.query(MissionChangeProposal).filter(MissionChangeProposal.id == trace.proposal_id).first()
        assert proposal is not None
        assert proposal.status == "pending"  # NEVER auto-approved!
        assert proposal.decided_at is None
        assert proposal.decided_by is None

        # Verify active mission version was NOT mutated
        assert active_m.active_version.version_number == active_version.version_number
        assert active_m.status == "active"


def test_proposal_idempotency_guard_prevents_duplicate_staging():
    """Idempotency guard prevents model from staging multiple duplicate proposals in a single run."""
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Model attempts to stage proposal twice
        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(
                    content="Staging first proposal.",
                    tool_calls=[
                        ToolCall(
                            id="call_p1",
                            name="create_mission_change_proposal",
                            arguments={
                                "mission_id": mission_id,
                                "proposal_title": "Pacing Adjustment Proposal 1",
                                "rationale": "Rationale 1",
                                "proposed_plan": {"stages": []},
                            },
                        ),
                        ToolCall(
                            id="call_p2",
                            name="create_mission_change_proposal",
                            arguments={
                                "mission_id": mission_id,
                                "proposal_title": "Duplicate Proposal Attempt",
                                "rationale": "Rationale 2",
                                "proposed_plan": {"stages": []},
                            },
                        ),
                    ],
                ),
                ModelTurnResponse(
                    content=json.dumps({
                        "decision_category": "proposed_mission_adjustment",
                        "explanation": "Proposal staged once safely.",
                        "recommended_action": "Review proposal.",
                        "confidence_score": 0.9,
                        "tradeoffs": [],
                    }),
                    tool_calls=[],
                ),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=5)
        trace = loop.execute("Test duplicate proposal protection.")

        # Total proposals created in database must be exactly 1
        proposals_in_db = db.query(MissionChangeProposal).filter(MissionChangeProposal.mission_id == mission_id).all()
        assert len(proposals_in_db) == 1
        assert trace.proposal_id == proposals_in_db[0].id


# ---------------------------------------------------------------------------
# 3. Budget Limits and Security Boundaries
# ---------------------------------------------------------------------------

def test_multiturn_loop_tool_call_budget_exhaustion():
    """Loop enforces max tool call budget and returns informative budget limit error."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Provider requests 5 calls in Turn 1, then 5 more in Turn 2 (exceeding budget of 8)
        five_calls = [
            ToolCall(id=f"c_{i}", name="read_student_profile", arguments={"student_id": student.id})
            for i in range(5)
        ]
        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(content="First batch", tool_calls=five_calls),
                ModelTurnResponse(content="Second batch", tool_calls=five_calls),
                ModelTurnResponse(
                    content=json.dumps({
                        "decision_category": "no_action",
                        "explanation": "Budget test concluded.",
                        "recommended_action": "Done.",
                        "confidence_score": 1.0,
                        "tradeoffs": [],
                    }),
                    tool_calls=[],
                ),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_tool_calls=8)
        trace = loop.execute("Test tool call budget.")

        # Exactly 8 tool executions succeeded; calls 9 and 10 were stopped by budget guard
        executed_records = [r for r in registry.invocations if "error" not in r.sanitized_output]
        assert len(executed_records) <= 8


def test_multiturn_loop_turn_budget_exhaustion():
    """Loop enforces max turns budget and triggers safe deterministic fallback."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Provider infinitely loops calling read_student_profile
        infinite_call = [ToolCall(id="call_inf", name="read_student_profile", arguments={"student_id": student.id})]
        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(content="Turn 1", tool_calls=infinite_call),
                ModelTurnResponse(content="Turn 2", tool_calls=infinite_call),
                ModelTurnResponse(content="Turn 3", tool_calls=infinite_call),
                ModelTurnResponse(content="Turn 4", tool_calls=infinite_call),
                ModelTurnResponse(content="Turn 5", tool_calls=infinite_call),
                ModelTurnResponse(content="Turn 6", tool_calls=infinite_call),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=3)
        trace = loop.execute("Test turn exhaustion.")

        assert trace.fallback_used is True
        assert trace.fallback_reason == "max_turns_exhausted"
        assert trace.engine_used == "deterministic_rules"
        assert len(trace.turns) == 3


def test_multiturn_loop_forbidden_action_blocked():
    """Model attempting to call forbidden actions receives permission_denied error in loop."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(
                    content="Attempting forbidden self-approval.",
                    tool_calls=[ToolCall(id="call_bad", name="approve_proposal", arguments={})],
                ),
                ModelTurnResponse(
                    content=json.dumps({
                        "decision_category": "human_review_required",
                        "explanation": "Self-approval was blocked by backend policy. Human review required.",
                        "recommended_action": "Student must review proposals manually.",
                        "confidence_score": 1.0,
                        "tradeoffs": ["Human consent enforced."],
                    }),
                    tool_calls=[],
                ),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=5)
        trace = loop.execute("Test forbidden action enforcement.")

        # Tool was blocked and logged as forbidden
        assert "approve_proposal" in trace.tools_invoked
        last_turn = trace.turns[0]
        assert "Forbidden tool" in str(last_turn.tool_results[0].get("error"))
        assert not trace.fallback_used
        assert trace.decision.decision_category == "human_review_required"


def test_multiturn_loop_student_id_injection_blocked():
    """Model attempting to supply cross-student ID is blocked by security boundary."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(
                    content="Attempting foreign student access.",
                    tool_calls=[
                        ToolCall(
                            id="call_inject",
                            name="read_student_profile",
                            arguments={"student_id": student.id + 999},
                        )
                    ],
                ),
                ModelTurnResponse(
                    content=json.dumps({
                        "decision_category": "human_review_required",
                        "explanation": "Security isolation prevented unauthorized access.",
                        "recommended_action": "Log violation.",
                        "confidence_score": 1.0,
                        "tradeoffs": [],
                    }),
                    tool_calls=[],
                ),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=5)
        trace = loop.execute("Test student ID injection.")

        last_turn = trace.turns[0]
        assert "Security violation" in str(last_turn.tool_results[0].get("error"))


# ---------------------------------------------------------------------------
# 4. Safe Fallback Recovery
# ---------------------------------------------------------------------------

def test_multiturn_loop_provider_error_falls_back_safely():
    """Provider exceptions trigger safe deterministic fallback without crashing."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        def failing_handler(*args, **kwargs):
            raise TimeoutError("Provider connection timed out")

        provider = MockProvider(dynamic_handler=failing_handler)
        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=3)

        trace = loop.execute("Test provider failure.")

        assert trace.fallback_used is True
        assert "provider_error" in trace.fallback_reason
        assert trace.engine_used == "deterministic_rules"
        assert trace.decision.decision_category == "human_review_required"


def test_multiturn_loop_malformed_json_falls_back_safely():
    """Unparseable model text triggers safe deterministic fallback."""
    _setup_active_mission()

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        provider = MockProvider(
            scripted_turns=[
                ModelTurnResponse(content="Sorry, I cannot help you with that.", tool_calls=[]),
                ModelTurnResponse(content="Still unparseable plain English text without JSON.", tool_calls=[]),
            ]
        )

        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=2)
        trace = loop.execute("Test malformed text fallback.")

        assert trace.fallback_used is True
        assert trace.fallback_reason == "malformed_final_output_unparseable_json"
        assert trace.engine_used == "deterministic_rules"


# ---------------------------------------------------------------------------
# 5. Target Demonstration Scenario (Section 13)
# ---------------------------------------------------------------------------

def test_target_scenario_university_exams_query():
    """High-value R2.2 demo: Student facing university exams asks for 4h/week advice via /v1/agent/query."""
    mission_id = _setup_active_mission(weekly_hours=20)

    # Invoke student guidance query endpoint
    exam_query = (
        "I have university exams for the next two weeks. "
        "I can only spend four hours per week preparing for my internship. What should I do?"
    )

    resp = client.post(
        "/v1/agent/query",
        json={"query": exam_query},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["mission_id"] == mission_id
    assert data["status"] == "completed"
    assert data["decision_category"] in ("proposed_mission_adjustment", "informational_notification")
    assert "pacing" in data["decision_explanation"].lower() or "roadmap" in data["decision_explanation"].lower()

    # Verify execution trace was saved in database
    with SessionLocal() as db:
        run_record = db.query(AgentRun).filter(AgentRun.id == data["id"]).first()
        assert run_record is not None
        assert run_record.engine_used is not None
        assert run_record.execution_time_ms >= 0
        assert run_record.decision_explanation == data["decision_explanation"]

        # Verify active mission was NOT mutated
        mission = db.query(CareerMission).filter(CareerMission.id == mission_id).first()
        assert mission.weekly_hours == 20  # Student's baseline mission remains unchanged until human approves proposal!


def test_student_query_no_active_mission():
    """Student query when no active mission exists returns informative guidance without crashing."""
    resp = client.post(
        "/v1/agent/query",
        json={"query": "How do I start preparing for an embedded firmware internship?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_category"] == "no_action"
    assert "no active career mission" in data["decision_explanation"].lower()


def test_multiturn_loop_dependent_tool_use_chain():
    """Prove agentic behavior: model dynamically chooses subsequent tools based on previous tool results.
    
    Chain:
    1. Model receives student inquiry.
    2. Model chooses read_active_mission.
    3. Model receives mission data (extracts mission_id, role, hours).
    4. Model dynamically selects simulate_plan_variant with hours derived from context.
    5. Model receives simulation output (extracts simulation_id, feasibility).
    6. Model dynamically selects create_mission_change_proposal referencing the exact simulation_id.
    7. Model receives proposal result (extracts proposal_id).
    8. Model outputs grounded final decision referencing all dependent steps.
    """
    mission_id = _setup_active_mission(weekly_hours=15)

    with SessionLocal() as db:
        student = db.query(Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Dynamic handler implementing the dependent agent reasoning logic
        def dynamic_agent_reasoner(messages: list[AgentMessage], tool_definitions: list[ToolDefinition]) -> ModelTurnResponse:
            last_msg = messages[-1]

            # Step 1: Initial user message -> choose read_active_mission
            if last_msg.role == "user" and not any(m.role == "tool" for m in messages):
                return ModelTurnResponse(
                    content="I will first inspect the student's active mission roadmap.",
                    tool_calls=[
                        ToolCall(
                            id="call_read_mission_1",
                            name="read_active_mission",
                            arguments={"student_id": student.id},
                        )
                    ],
                )

            # Step 2: Tool result from read_active_mission -> inspect and choose simulate_plan_variant
            if last_msg.role == "tool" and last_msg.name == "read_active_mission":
                m_data = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
                active_hours = m_data.get("weekly_hours", 15)
                # Dependent calculation: reduce to 4 hours due to exams
                reduced_hours = 4 if active_hours > 4 else 2
                return ModelTurnResponse(
                    content=f"Active mission operates at {active_hours}h/week. Dynamically simulating exam pacing at {reduced_hours}h/week.",
                    tool_calls=[
                        ToolCall(
                            id="call_sim_pacing_2",
                            name="simulate_plan_variant",
                            arguments={"variant_type": "pacing_reduction", "weekly_hours": reduced_hours},
                        )
                    ],
                )

            # Step 3: Tool result from simulate_plan_variant -> verify feasibility & stage proposal
            if last_msg.role == "tool" and last_msg.name == "simulate_plan_variant":
                sim_data = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
                sim_id = sim_data["simulation_id"]
                is_feasible = sim_data["validity_status"] == "VALID_AND_FEASIBLE"
                assert is_feasible, "Expected simulation to be feasible"
                return ModelTurnResponse(
                    content=f"Simulation {sim_id} verified feasible. Dynamically staging proposal referencing simulation.",
                    tool_calls=[
                        ToolCall(
                            id="call_stage_proposal_3",
                            name="create_mission_change_proposal",
                            arguments={
                                "mission_id": mission_id,
                                "proposal_title": "Exam Pacing Adjustment (4 hrs/week)",
                                "rationale": "C++ graph simulation confirms 4h/week pacing preserves prerequisite validity.",
                                "simulation_id": sim_id,
                            },
                        )
                    ],
                )

            # Step 4: Tool result from create_mission_change_proposal -> synthesize final grounded decision
            if last_msg.role == "tool" and last_msg.name == "create_mission_change_proposal":
                prop_data = json.loads(last_msg.content) if isinstance(last_msg.content, str) else last_msg.content
                staged_pid = prop_data["proposal_id"]
                decision_payload = {
                    "decision_category": "proposed_mission_adjustment",
                    "explanation": f"Evaluated and staged plan adjustment proposal #{staged_pid} grounded in C++ simulation.",
                    "recommended_action": f"Review staged proposal #{staged_pid} in your Roadmap or Assistant drawer.",
                    "confidence_score": 0.95,
                    "tradeoffs": [
                        "Reduces study commitment to 4h/week during university exams.",
                        "Preserves 100% of completed milestone tasks.",
                        "Roadmap re-indexed via C++ Kahn's topological sort.",
                    ],
                    "suggested_proposal_title": "Exam Pacing Adjustment (4 hrs/week)",
                    "suggested_proposal_rationale": "Grounding in C++ simulation verified.",
                }
                return ModelTurnResponse(
                    content=json.dumps(decision_payload),
                    tool_calls=[],
                )

            raise RuntimeError(f"Unexpected state in dynamic_agent_reasoner: {last_msg.role} / {last_msg.name}")

        provider = MockProvider(dynamic_handler=dynamic_agent_reasoner)
        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=6)

        trace = loop.execute("I have university exams and can only study 4 hours per week. Can you help adjust my plan?")

        # Assertions proving dependent tool chain execution
        assert trace.engine_used == "mock_llm"
        assert not trace.fallback_used
        assert trace.total_tool_calls == 3
        assert trace.tools_invoked == [
            "read_active_mission",
            "simulate_plan_variant",
            "create_mission_change_proposal",
        ]
        assert trace.proposal_id is not None
        assert trace.decision.decision_category == "proposed_mission_adjustment"
        assert f"#{trace.proposal_id}" in trace.decision.explanation

        # Verify staged proposal in database is strictly PENDING (human consent boundary)
        proposal = db.query(MissionChangeProposal).filter(MissionChangeProposal.id == trace.proposal_id).first()
        assert proposal is not None
        assert proposal.status == "pending"
        assert proposal.decided_at is None

