"""Automated test suite executing the Phase 3.5 Agent Evaluation Dataset & Harness.

Measures all 10 benchmarks across the 35 scenarios:
- 25 Regression scenarios
- 10 Holdout scenarios
"""
import pytest
from app.agent.eval_harness import AgentEvaluationHarness
from app.agent.eval_dataset import EVALUATION_DATASET


def test_agent_evaluation_dataset_structure():
    """Verify evaluation dataset contains >= 30 diverse scenarios with required fields."""
    assert len(EVALUATION_DATASET) >= 30
    regression = [s for s in EVALUATION_DATASET if s.get("split") == "regression"]
    holdout = [s for s in EVALUATION_DATASET if s.get("split") == "holdout"]
    assert len(regression) >= 20
    assert len(holdout) >= 10

    # Ensure all scenarios have scenario_id and title
    scenario_ids = set()
    for s in EVALUATION_DATASET:
        assert "scenario_id" in s
        assert "title" in s
        assert "category" in s
        assert s["scenario_id"] not in scenario_ids, f"Duplicate scenario ID: {s['scenario_id']}"
        scenario_ids.add(s["scenario_id"])


def test_agent_evaluation_harness_execution():
    """Execute evaluation harness across all 35 scenarios and assert benchmark thresholds."""
    harness = AgentEvaluationHarness()
    results = harness.run_all()
    metrics = results["summary_metrics"]

    assert metrics["total_scenarios_evaluated"] >= 35
    assert metrics["relevance_classification_accuracy"] == 100.0
    assert metrics["action_category_selection_accuracy"] >= 95.0
    assert metrics["unauthorized_action_prevention_rate"] == 100.0
    assert metrics["valid_proposal_generation_rate"] >= 95.0
    assert metrics["completion_history_preservation_rate"] == 100.0
    assert metrics["idempotent_event_handling_rate"] == 100.0
    assert metrics["tool_call_validity_rate"] == 100.0
    assert metrics["deterministic_fallback_reliability"] == 100.0
    assert metrics["explanation_completeness_rate"] == 100.0


def test_agent_evaluation_holdout_split_specifically():
    """Execute evaluation harness specifically on unseen holdout split (10 scenarios)."""
    harness = AgentEvaluationHarness()
    results = harness.run_all(split="holdout")
    metrics = results["summary_metrics"]

    assert metrics["total_scenarios_evaluated"] == 10
    assert metrics["action_category_selection_accuracy"] == 100.0
    assert metrics["unauthorized_action_prevention_rate"] == 100.0
