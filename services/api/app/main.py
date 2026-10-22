from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .bridge import EngineUnavailable, run_matching
from .schemas import MatchRequest, MatchResponse

app = FastAPI(title="InternPath AI API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.get("/health")
def health():
    return {"service": "internpath-api", "status": "ok", "version": "phase-1"}

@app.post("/v1/demo/match", response_model=MatchResponse)
def demo_match(payload: MatchRequest):
    try:
        return run_matching(payload)
    except EngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
