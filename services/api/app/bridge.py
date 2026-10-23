"""Phase 1 & Phase 3.1 boundary: validated API request -> C++ CLI subprocess -> JSON response.

The argument transport passes safe, strictly validated numeric flags directly to CreateProcessW
(shell=False), completely precluding shell injection vulnerabilities.
"""
import json
import os
from pathlib import Path
import subprocess
from .schemas import (
    MatchRequest,
    MatchResponse,
    TargetSkillInput,
    StudentSkillInput,
    LearningPathResponse,
)

class EngineUnavailable(RuntimeError):
    pass

ROOT = Path(__file__).resolve().parents[3]

def engine_path() -> Path:
    configured = os.getenv("INTERNPATH_DSA_BIN")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [
        ROOT / "build/engine/internpath_dsa",
        ROOT / "build/engine/internpath_dsa.exe",
        ROOT / "build/engine/Release/internpath_dsa.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise EngineUnavailable("C++ engine not built. See README: compile with CMake first.")

def run_matching(req: MatchRequest) -> MatchResponse:
    path = engine_path()
    arguments = [str(path)]
    for flag, items in [
        ("--student", req.student_levels),
        ("--required", req.required_levels),
        ("--weights", req.weights),
        ("--mandatory", req.mandatory),
    ]:
        arguments.extend([flag, ",".join(map(str, items))])
    try:
        process = subprocess.run(arguments, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineUnavailable("Failed to run C++ engine") from exc
    if process.returncode != 0:
        raise EngineUnavailable("C++ engine rejected the request")
    try:
        return MatchResponse.model_validate(json.loads(process.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        raise EngineUnavailable("C++ engine returned invalid JSON") from exc

def run_learning_path_with_graph(
    skills: list[dict],
    prerequisites: list[tuple[int, int]],
    targets: list[TargetSkillInput],
    student: list[StudentSkillInput],
) -> LearningPathResponse:
    """Execute LearningPathEngine by streaming dynamic curriculum graph from DB over stdin."""
    path = engine_path()
    arguments = [str(path), "--plan-stdin"]

    payload = {
        "skills": [
            {
                "id": s["id"],
                "name": s["name"],
                "category": s["category"],
                "max_level": s.get("max_level", 3),
                "description": s.get("description", ""),
            }
            for s in skills
        ],
        "prerequisites": [
            {"prereq_id": p[0], "skill_id": p[1]}
            for p in prerequisites
        ],
        "targets": [
            {
                "skill_id": t["skill_id"] if isinstance(t, dict) else t.skill_id,
                "required_level": t["required_level"] if isinstance(t, dict) else t.required_level,
                "mandatory": True,
                "role_context": (
                    t.get("role_context", "Target Requirement")
                    if isinstance(t, dict)
                    else getattr(t, "role_context", "Target Requirement")
                ),
            }
            for t in targets
        ],
        "student_skills": [
            {
                "skill_id": s["skill_id"] if isinstance(s, dict) else s.skill_id,
                "declared_level": s["level"] if isinstance(s, dict) else s.level,
                "verified_level": (
                    (s["level"] if s.get("is_verified", False) else 0)
                    if isinstance(s, dict)
                    else (s.level if s.is_verified else 0)
                ),
                "is_verified": s["is_verified"] if isinstance(s, dict) else s.is_verified,
            }
            for s in student
        ],
    }

    payload_json = json.dumps(payload)

    try:
        process = subprocess.run(
            arguments,
            input=payload_json,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineUnavailable("Failed to execute C++ engine subprocess") from exc

    if process.returncode != 0:
        error_msg = process.stderr.strip() if process.stderr else "C++ engine rejected dynamic graph plan"
        raise EngineUnavailable(error_msg)

    try:
        raw_json = json.loads(process.stdout)
        return LearningPathResponse.model_validate(raw_json)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EngineUnavailable("C++ engine emitted malformed JSON response") from exc


def run_learning_path(
    targets: list[TargetSkillInput],
    student: list[StudentSkillInput]
) -> LearningPathResponse:
    path = engine_path()
    arguments = [str(path), "--plan"]

    if targets:
        target_tokens = [f"{t.skill_id}:{t.required_level}" for t in targets]
        arguments.extend(["--target", ",".join(target_tokens)])

    if student:
        student_tokens = [
            f"{s.skill_id}:{s.level}:{'v' if s.is_verified else 'u'}"
            for s in student
        ]
        arguments.extend(["--student", ",".join(student_tokens)])

    try:
        process = subprocess.run(arguments, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineUnavailable("Failed to execute C++ engine subprocess") from exc

    if process.returncode != 0:
        error_msg = process.stderr.strip() if process.stderr else "C++ engine rejected the plan request"
        raise EngineUnavailable(error_msg)

    try:
        raw_json = json.loads(process.stdout)
        return LearningPathResponse.model_validate(raw_json)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EngineUnavailable("C++ engine emitted malformed JSON response") from exc

