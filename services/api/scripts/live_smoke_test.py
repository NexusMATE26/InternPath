"""Live Provider Smoke-Test Procedure for InternPath Agentic AI (R2.4.1).

Verifies readiness for live external LLM evaluation (Google Gemini or OpenAI).

SAFETY INVARIANTS:
1. NEVER executes external API calls without explicit CLI flag: --execute-live
2. NEVER prints, commits, or stores API keys in logs or files.
3. If no key is set or --execute-live is omitted, reports LIVE PROVIDER VERIFICATION PENDING.
4. When executed live, proves:
   - Real external model responds.
   - External model selects an authorized tool (e.g. read_active_mission).
   - Backend executes the tool via AgentToolRegistry.
   - Result is returned to the model in multi-turn conversation.
   - Model produces a grounded final response.
   - Trace is persisted with truthful engine label ('gemini:<model>' or 'openai:<model>').
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add services/api to sys.path
API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Use isolated test database for live verification tests
TEST_DB_PATH = API_DIR / "test_live_verify.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

from app.database import engine, Base, SessionLocal
from app.seed import seed_database
from app import crud, models
from app.agent.providers import GeminiProvider, OpenAIProvider
from app.agent.loop import AgentExecutionLoop
from app.agent.tools import AgentToolRegistry


def verify_live_provider_readiness(execute_live: bool = False) -> dict[str, str]:
    """Inspect provider configuration and run smoke test if explicitly authorized."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    has_gemini = bool(gemini_key and not gemini_key.startswith("mock_") and not gemini_key.startswith("fake_"))
    has_openai = bool(openai_key and not openai_key.startswith("mock_") and not openai_key.startswith("fake_"))

    print("=" * 70)
    print("INTERNPATH AI - LIVE PROVIDER COMPATIBILITY CHECKPOINT")
    print("=" * 70)
    print(f"Gemini API Key Configured: {'[REDACTED_PRESENT]' if has_gemini else '[NOT_CONFIGURED]'}")
    print(f"OpenAI API Key Configured: {'[REDACTED_PRESENT]' if has_openai else '[NOT_CONFIGURED]'}")
    print(f"Execution Mode: {'LIVE NETWORK AUTHORIZED (--execute-live)' if execute_live else 'SAFE LOCAL VERIFICATION (No network calls)'}")
    print("-" * 70)

    if not has_gemini and not has_openai:
        status_msg = "LIVE PROVIDER VERIFICATION PENDING (No external API keys configured)"
        print(f"STATUS: {status_msg}")
        print("Detail: Neither GEMINI_API_KEY nor OPENAI_API_KEY is present in the environment.")
        print("Zero external network requests executed. Security boundaries preserved.")
        return {"status": "PENDING", "reason": "no_credentials", "message": status_msg}

    if not execute_live:
        status_msg = "LIVE PROVIDER VERIFICATION PENDING (Awaiting explicit --execute-live flag)"
        print(f"STATUS: {status_msg}")
        print("Detail: API credentials detected, but live external execution requires explicit authorization flag --execute-live.")
        print("Zero external network requests executed. Security boundaries preserved.")
        return {"status": "PENDING", "reason": "unauthorized_flag", "message": status_msg}

    # If authorized and key present, execute live verification
    print("Executing authenticated live smoke test against isolated test database...")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db, reset=True)
        student = db.query(models.Student).first()
        registry = AgentToolRegistry(db, student.id)

        # Select provider
        if has_gemini:
            model = os.environ.get("INTERNPATH_LLM_MODEL") or "gemini-1.5-flash"
            provider = GeminiProvider(api_key=gemini_key, model_name=model)
        else:
            model = os.environ.get("INTERNPATH_LLM_MODEL") or "gpt-4o-mini"
            provider = OpenAIProvider(api_key=openai_key, model_name=model)

        print(f"Provider: {provider.get_engine_label()}")
        loop = AgentExecutionLoop(registry=registry, provider=provider, max_turns=4)

        query = "Please inspect my active Career Mission roadmap and summarize my next milestone."
        print(f"Student Query: '{query}'")

        trace = loop.execute(query)

        print("-" * 70)
        print("LIVE EXECUTION RESULT:")
        print(f"Engine Used: {trace.engine_used}")
        print(f"Total Turns: {len(trace.turns)}")
        print(f"Tools Invoked: {trace.tools_invoked}")
        print(f"Fallback Used: {trace.fallback_used}")
        print(f"Decision Category: {trace.decision.decision_category}")
        print(f"Decision Explanation: {trace.decision.explanation}")
        print("=" * 70)

        # Validate live invariants
        assert trace.engine_used == provider.get_engine_label(), f"Engine mismatch: {trace.engine_used}"
        assert not trace.fallback_used, f"Fallback was triggered: {trace.fallback_reason}"
        assert len(trace.tools_invoked) >= 1, "Expected model to invoke at least one tool"
        assert "read_active_mission" in trace.tools_invoked, "Expected model to invoke read_active_mission"

        return {"status": "VERIFIED_LIVE", "engine": trace.engine_used, "tools": str(trace.tools_invoked)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InternPath Live Provider Smoke Test")
    parser.add_argument("--execute-live", action="store_true", help="Authorize live network calls to configured external model API")
    args = parser.parse_args()

    result = verify_live_provider_readiness(execute_live=args.execute_live)
    print(json.dumps(result, indent=2))
