"""Initialize an isolated test demo database for end-to-end verification."""
import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

DEMO_DB_PATH = API_DIR / "test_demo_isolated.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DEMO_DB_PATH.as_posix()}"

from app.database import engine, Base, SessionLocal
from app.seed import seed_database
from app import crud, models


def main():
    print(f"Creating isolated test database at: {DEMO_DB_PATH}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db, reset=True)
    
    # Use FastAPI client to create active career mission using C++ planner
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post(
        "/v1/missions",
        json={
            "target_role_id": "distributed-systems-intern",
            "weekly_hours": 15,
        },
    )
    if resp.status_code == 201:
        print(f"Active Career Mission created successfully: ID {resp.json().get('id')}")
    else:
        print(f"Mission creation response: {resp.status_code} - {resp.text}")
    print("Isolated test demo database seeded successfully.")


if __name__ == "__main__":
    main()
