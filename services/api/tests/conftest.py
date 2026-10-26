import os
from pathlib import Path
import pytest

# Ensure isolated test database is used for all test executions
TEST_DB_PATH = Path(__file__).resolve().parents[1] / "test_internpath.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

from app.database import engine, Base, SessionLocal
from app.seed import seed_database
import app.models  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create and seed dedicated isolated test database for test session."""
    # Ensure fresh test database tables
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db, reset=True)
    yield
    # Dispose engine and remove test database file after session
    engine.dispose()
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
