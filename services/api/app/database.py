import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Load .env file from services/api/.env or repo root .env if present
ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / "services" / "api" / ".env"
if ENV_FILE.is_file():
    load_dotenv(ENV_FILE)
else:
    load_dotenv(ROOT_DIR / ".env")

API_DIR = Path(__file__).resolve().parents[1]
raw_db_url = os.getenv("DATABASE_URL")
if not raw_db_url:
    DATABASE_URL = f"sqlite:///{API_DIR.joinpath('internpath.db').as_posix()}"
elif raw_db_url.startswith("sqlite:///./"):
    rel_path = raw_db_url[len("sqlite:///./"):]
    DATABASE_URL = f"sqlite:///{API_DIR.joinpath(rel_path).as_posix()}"
else:
    DATABASE_URL = raw_db_url

# Fail-closed guard: prevent test execution from inadvertently using development database
if ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ) and "test" not in DATABASE_URL.lower():
    raise RuntimeError(
        f"SAFETY GATE ENFORCED: Attempted to initialize database engine for tests with non-test database: {DATABASE_URL}. "
        "Test runs must explicitly specify an isolated test database."
    )


# Engine configuration
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# Enable foreign keys for SQLite
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
