"""Deterministic deadline-impact evaluator and decision logic for InternPath AI.

Calculates feasibility, remaining effort, required pacing, and decides between:
- no_action
- informational_notification
- proposed_mission_adjustment
- human_review_required

Enforces realistic undergraduate student study limits (avoiding excessive pacing > 25 hrs/week),
prioritizes mandatory competencies when runway is constrained, and communicates uncertainty.
"""
from datetime import datetime, timezone
from typing import Optional, Any

from app.agent.clock import get_utc_now, parse_datetime_safe


def calculate_deadline_metrics(
    current_deadline: Optional[str],
    new_deadline: Optional[str],
    weekly_hours: int,
    remaining_tasks: list[dict[str, Any]],
    total_tasks_count: int = 0,
    completed_tasks_count: int = 0,
    source_reliability: str = "verified_employer",
    is_role_relevant: bool = True,
    mission_status: str = "active",
    reference_date: Optional[datetime] = None,
) -> dict[str, Any]:
    """Calculate deterministic pacing metrics, feasibility, and decision category.

    Returns:
        dict containing:
        - decision_category: str
        - explanation: str
        - recommended_action: str
        - metrics: dict with days_remaining, weeks_remaining, remaining_effort_hours,
                   required_weekly_hours, capacity_ratio, pace_change_percent,
                   uncertainty_range, feasibility_status
    """
    ref_dt = reference_date or get_utc_now()
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    else:
        ref_dt = ref_dt.astimezone(timezone.utc)

    # 1. Relevance Assessment
    if not is_role_relevant:
        return {
            "decision_category": "no_action",
            "explanation": (
                "The target role for this internship event does not match the student's active "
                "Career Mission. No plan alteration or schedule re-balancing is required."
            ),
            "recommended_action": "Log event as processed with no impact.",
            "metrics": {
                "is_role_relevant": False,
                "mission_status": mission_status,
            },
        }

    # 2. Mission status check (already completed or archived)
    if mission_status != "active":
        return {
            "decision_category": "no_action",
            "explanation": (
                f"Student's Career Mission is currently '{mission_status}'. "
                "Schedule adjustments are only evaluated against active career roadmaps."
            ),
            "recommended_action": "No action needed for inactive mission.",
            "metrics": {
                "mission_status": mission_status,
                "is_role_relevant": True,
            },
        }

    if total_tasks_count > 0 and completed_tasks_count >= total_tasks_count:
        return {
            "decision_category": "no_action",
            "explanation": (
                f"Student has already achieved 100% completion ({completed_tasks_count}/{total_tasks_count} tasks) "
                "on their approved Career Mission roadmap. The deadline change does not impact readiness."
            ),
            "recommended_action": "Congratulate student or invite them to archive/advance mission.",
            "metrics": {
                "progress_percent": 100.0,
                "completed_tasks": completed_tasks_count,
                "total_tasks": total_tasks_count,
            },
        }

    # 3. Source reliability check
    if source_reliability == "unverified_third_party":
        return {
            "decision_category": "human_review_required",
            "explanation": (
                "The internship deadline update was reported by an unverified third-party source. "
                "To prevent disruption to the student's approved roadmap, human verification is required "
                "before altering milestones."
            ),
            "recommended_action": "Flag for student/advisor verification of employer announcement.",
            "metrics": {
                "source_reliability": source_reliability,
            },
        }

    # 4. Deadline date validation
    if not new_deadline or (isinstance(new_deadline, str) and not new_deadline.strip()):
        return {
            "decision_category": "human_review_required",
            "explanation": (
                "The deadline-change event is missing a target application deadline date. "
                "Cannot compute remaining preparation runway without a verified date."
            ),
            "recommended_action": "Request valid deadline date from event source or student.",
            "metrics": {
                "error": "missing_deadline",
            },
        }

    parsed_new = parse_datetime_safe(new_deadline)
    if not parsed_new:
        return {
            "decision_category": "human_review_required",
            "explanation": (
                f"The provided deadline date '{new_deadline}' is not in a valid date/time format. "
                "Cannot compute scheduling runway."
            ),
            "recommended_action": "Provide date in standard ISO format (e.g. YYYY-MM-DD).",
            "metrics": {
                "error": "invalid_deadline_format",
                "raw_value": new_deadline,
            },
        }

    # 5. Student weekly hours validation
    if weekly_hours is None or weekly_hours <= 0:
        return {
            "decision_category": "human_review_required",
            "explanation": (
                f"Student weekly preparation availability is configured as {weekly_hours} hrs/week. "
                "A positive weekly study capacity is required to calculate feasibility and pacing."
            ),
            "recommended_action": "Student must update weekly available hours in profile settings.",
            "metrics": {
                "weekly_hours": weekly_hours,
                "error": "zero_or_negative_weekly_hours",
            },
        }

    # 6. Time delta calculations
    delta = parsed_new - ref_dt
    days_remaining = delta.total_seconds() / 86400.0

    if days_remaining <= 0:
        return {
            "decision_category": "human_review_required",
            "explanation": (
                f"The new application deadline ({parsed_new.strftime('%Y-%m-%d')}) has expired or occurs today "
                f"({days_remaining:.1f} days remaining). Automatic rescheduling cannot guarantee readiness."
            ),
            "recommended_action": "Student should review immediate submission options or target next internship intake.",
            "metrics": {
                "days_remaining": round(days_remaining, 1),
                "deadline": parsed_new.isoformat(),
                "feasibility_status": "expired",
            },
        }

    # Check if new deadline is identical to previous deadline
    parsed_prev = parse_datetime_safe(current_deadline)
    if parsed_prev and parsed_new.date() == parsed_prev.date():
        return {
            "decision_category": "no_action",
            "explanation": (
                f"The reported deadline ({parsed_new.strftime('%Y-%m-%d')}) is identical to the currently recorded "
                f"deadline. Active mission schedule requires no modifications."
            ),
            "recommended_action": "Log event as processed with no changes.",
            "metrics": {
                "days_remaining": round(days_remaining, 1),
                "deadline": parsed_new.isoformat(),
            },
        }

    weeks_remaining = max(days_remaining / 7.0, 0.14)  # Min ~1 day

    # 7. Remaining effort calculation & uncertainty analysis
    rem_min = sum(t.get("estimated_hours_min", 0) for t in remaining_tasks)
    rem_max = sum(t.get("estimated_hours_max", 0) for t in remaining_tasks)
    if rem_max == 0 and rem_min == 0:
        rem_avg = float(len(remaining_tasks) * 10)  # Reasonable fallback if task hours unconfigured
        rem_min = rem_avg * 0.8
        rem_max = rem_avg * 1.2
    else:
        rem_avg = float(rem_min + rem_max) / 2.0

    if rem_avg <= 0 or len(remaining_tasks) == 0:
        return {
            "decision_category": "no_action",
            "explanation": (
                "There are no uncompleted milestone tasks remaining on the active roadmap. "
                "The revised deadline does not impact current workload."
            ),
            "recommended_action": "No plan alteration required.",
            "metrics": {
                "remaining_tasks_count": len(remaining_tasks),
                "remaining_effort_hours": 0.0,
            },
        }

    # Distinguish mandatory vs optional tasks for realistic scope reduction
    mandatory_tasks = [t for t in remaining_tasks if t.get("is_mandatory", True)]
    optional_tasks = [t for t in remaining_tasks if not t.get("is_mandatory", True)]
    mand_min = sum(t.get("estimated_hours_min", 0) for t in mandatory_tasks)
    mand_max = sum(t.get("estimated_hours_max", 0) for t in mandatory_tasks)
    if mand_max == 0 and mand_min == 0:
        mand_avg = float(len(mandatory_tasks) * 10)
    else:
        mand_avg = float(mand_min + mand_max) / 2.0

    required_weekly_hours = rem_avg / weeks_remaining
    capacity_ratio = required_weekly_hours / float(weekly_hours)
    mandatory_weekly_hours = mand_avg / weeks_remaining
    mandatory_capacity_ratio = mandatory_weekly_hours / float(weekly_hours)

    # Previous deadline metrics for pacing diff
    prev_days = None
    prev_required_weekly = None
    pace_change_pct = None
    if parsed_prev:
        prev_delta = parsed_prev - ref_dt
        prev_days = prev_delta.total_seconds() / 86400.0
        if prev_days > 0:
            prev_weeks = max(prev_days / 7.0, 0.14)
            prev_required_weekly = rem_avg / prev_weeks
            if prev_required_weekly > 0:
                pace_change_pct = ((required_weekly_hours - prev_required_weekly) / prev_required_weekly) * 100.0

    metrics = {
        "days_remaining": round(days_remaining, 1),
        "weeks_remaining": round(weeks_remaining, 1),
        "remaining_effort_hours_min": rem_min,
        "remaining_effort_hours_max": rem_max,
        "remaining_effort_hours_avg": round(rem_avg, 1),
        "uncertainty_range": {"min_hours": round(rem_min, 1), "max_hours": round(rem_max, 1)},
        "weekly_hours_capacity": weekly_hours,
        "required_weekly_hours": round(required_weekly_hours, 1),
        "capacity_ratio": round(capacity_ratio, 2),
        "mandatory_tasks_count": len(mandatory_tasks),
        "optional_tasks_count": len(optional_tasks),
        "mandatory_required_weekly_hours": round(mandatory_weekly_hours, 1),
        "mandatory_capacity_ratio": round(mandatory_capacity_ratio, 2),
        "previous_days_remaining": round(prev_days, 1) if prev_days is not None else None,
        "pace_change_percent": round(pace_change_pct, 1) if pace_change_pct is not None else None,
    }

    # 8. Realistic Decision Categorization
    # Rule 8A: If deadline extended significantly
    if parsed_prev and parsed_new > parsed_prev:
        metrics["feasibility_status"] = "extended_comfortable"
        return {
            "decision_category": "informational_notification",
            "explanation": (
                f"Application deadline was extended from {parsed_prev.strftime('%Y-%m-%d')} to "
                f"{parsed_new.strftime('%Y-%m-%d')} ({days_remaining:.0f} days remaining). "
                f"Required pacing eases to {required_weekly_hours:.1f} hrs/week (capacity: {weekly_hours} hrs/week). "
                "Current Career Mission roadmap remains fully sound and achievable with relaxed milestone buffers."
            ),
            "recommended_action": "Send informational notification; no urgent plan restructuring needed.",
            "metrics": metrics,
        }

    # Rule 8B: Infeasible extreme pace (cannot recommend > 40 hrs/week or > 2.6x capacity for student study)
    # Pacing above a 40 hr/week full-time study commitment or 2.6x capacity cannot be scheduled without human intervention.
    STUDENT_MAX_FEASIBLE_WEEKLY = 40.0
    STUDENT_MAX_CAPACITY_RATIO = 2.6

    if required_weekly_hours > STUDENT_MAX_FEASIBLE_WEEKLY or capacity_ratio > STUDENT_MAX_CAPACITY_RATIO:
        # Check if Scope Reduction is an option (deferring optional electives to focus on mandatory)
        if (
            len(optional_tasks) > 0
            and mandatory_weekly_hours <= STUDENT_MAX_FEASIBLE_WEEKLY
            and mandatory_capacity_ratio <= 1.5
        ):
            metrics["feasibility_status"] = "scope_reduction_recommended"
            metrics["scope_reduction_available"] = True
            return {
                "decision_category": "proposed_mission_adjustment",
                "explanation": (
                    f"Application deadline moved earlier to {parsed_new.strftime('%Y-%m-%d')} "
                    f"({days_remaining:.0f} days remaining). Completing all remaining tasks requires "
                    f"{required_weekly_hours:.1f} hrs/week ({capacity_ratio:.1f}x capacity), which exceeds healthy limits. "
                    f"However, scope reduction is achievable: prioritizing {len(mandatory_tasks)} mandatory competencies "
                    f"and deferring {len(optional_tasks)} optional electives reduces pacing to {mandatory_weekly_hours:.1f} hrs/week "
                    f"({(mandatory_capacity_ratio * 100):.0f}% capacity). Staging an adjusted mission focusing on core readiness."
                ),
                "recommended_action": "Stage pending proposal focusing on core mandatory competencies.",
                "metrics": metrics,
            }

        # Otherwise, even mandatory tasks exceed realistic capacity -> Honest human review alert
        metrics["feasibility_status"] = "infeasible_excessive_pace"
        metrics["scope_reduction_available"] = False
        return {
            "decision_category": "human_review_required",
            "explanation": (
                f"Deadline moved drastically closer to {parsed_new.strftime('%Y-%m-%d')} "
                f"({days_remaining:.0f} days remaining). Meeting this deadline requires an unachievable "
                f"{required_weekly_hours:.1f} hrs/week ({capacity_ratio:.1f}x student's {weekly_hours} hrs/week capacity). "
                f"Even mandatory requirements alone demand {mandatory_weekly_hours:.1f} hrs/week. "
                "Human advisor guidance is required to prioritize essential competencies or identify alternative internship cycles. "
                "Guaranteed readiness cannot be promised within the remaining runway."
            ),
            "recommended_action": "Flag for human consultation; avoid making unrealistic readiness guarantees.",
            "metrics": metrics,
        }

    # Rule 8C: Manageable Acceleration requiring stage adjustment (capacity ratio > 1.15)
    if capacity_ratio > 1.15:
        metrics["feasibility_status"] = "manageable_acceleration"
        return {
            "decision_category": "proposed_mission_adjustment",
            "explanation": (
                f"Application deadline moved earlier to {parsed_new.strftime('%Y-%m-%d')} "
                f"({days_remaining:.0f} days remaining). Required study pacing increases to "
                f"{required_weekly_hours:.1f} hrs/week, exceeding student capacity ({weekly_hours} hrs/week) "
                f"by {((capacity_ratio - 1.0) * 100.0):.0f}%. "
                "A proposed mission adjustment has been generated to compress stages, accelerate core prerequisites, "
                "and maintain milestone feasibility."
            ),
            "recommended_action": "Stage pending mission change proposal for student approval.",
            "metrics": metrics,
        }

    # Rule 8D: Comfortable pacing (capacity ratio <= 1.15)
    metrics["feasibility_status"] = "comfortable"
    return {
        "decision_category": "informational_notification",
        "explanation": (
            f"Application deadline recorded as {parsed_new.strftime('%Y-%m-%d')} ({days_remaining:.0f} days remaining). "
            f"Required pacing is {required_weekly_hours:.1f} hrs/week, comfortably within student's "
            f"{weekly_hours} hrs/week availability (capacity utilization: {(capacity_ratio * 100):.0f}%). "
            "Approved roadmap milestones proceed unchanged."
        ),
        "recommended_action": "Log informational confirmation of feasible pacing.",
        "metrics": metrics,
    }
