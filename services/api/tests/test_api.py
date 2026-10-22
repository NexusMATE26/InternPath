from fastapi.testclient import TestClient
from app.main import app
from app.bridge import engine_path, EngineUnavailable

client = TestClient(app)

DEMO = {
    "student_levels": [2, 1, 0, 1],
    "required_levels": [2, 2, 1, 1],
    "weights": [5, 4, 3, 2],
    "mandatory": [1, 1, 0, 0]
}

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_invalid_request():
    bad = {**DEMO, "weights": [5]}
    assert client.post("/v1/demo/match", json=bad).status_code == 422

def test_match_end_to_end():
    # This is an integration test: compile the C++ executable before running.
    try:
        engine_path()
    except EngineUnavailable as exc:
        raise AssertionError("Compile the C++ engine first: " + str(exc)) from exc
    response = client.post("/v1/demo/match", json=DEMO)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["earned_points"] == 54
    assert out["max_points"] == 84
    assert out["missing_mandatory"] == 1
    assert out["mandatory_requirements_met"] is False
    assert abs(out["coverage_percent"] - 64.29) < 0.01
