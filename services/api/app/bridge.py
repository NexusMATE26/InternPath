"""Phase 1 boundary: validated JSON API request -> C++ CLI flags -> JSON response.

The argument transport is deliberately temporary, to avoid adding a third-party
C++ JSON dependency before verifying the full integration loop.
"""
import json
import os
from pathlib import Path
import subprocess
from .schemas import MatchRequest, MatchResponse

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
