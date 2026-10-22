# InternPath AI — Phase 1 Starter

One codebase for the DSA mini-project and InnovaX Agentic AI competition.

**What works today:** React interface → FastAPI endpoint → compiled C++20 matching executable → computed result returned to the browser. This is an intentionally narrow vertical slice: the AI agent, real posting ingestion, persistent student data, PostgreSQL models, and all nine handwritten DSAs are **not yet implemented**.

## Requirements

- Python **3.11+** (with `pip`)
- Node.js **20+** (with `npm`)
- CMake **3.20+** and a C++20 compiler (MSVC Build Tools or MinGW-w64 on Windows; GCC/Clang on Linux/macOS)
- Git and an editor (Google Antigravity, VS Code, etc.)

## 1. Compile and test the C++ engine

From the repository root in a terminal:

```bash
cmake -S engines/dsa -B build/engine
cmake --build build/engine --config Release
ctest --test-dir build/engine -C Release --output-on-failure
```

**Executable location:** on Linux/MinGW it is usually `build/engine/internpath_dsa` (or `.exe`). With Visual Studio/MSVC it is usually `build/engine/Release/internpath_dsa.exe`.

Run directly (choose your platform's executable path):

```bash
./build/engine/internpath_dsa --student 2,1,0,1 --required 2,2,1,1 --weights 5,4,3,2 --mandatory 1,1,0,0
```

Expected coverage is **64.29%** (54/84), with one missing mandatory requirement. The output is JSON.

## 2. Start the FastAPI server

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS alternative: source .venv/bin/activate
python -m pip install -r services/api/requirements.txt
python -m uvicorn app.main:app --app-dir services/api --reload --port 8000
```

**Important on Windows with Visual Studio:** before starting FastAPI, set the exact C++ executable path in your current PowerShell terminal:

```powershell
$env:INTERNPATH_DSA_BIN = (Resolve-Path '.\build\engine\Release\internpath_dsa.exe').Path
```

For MinGW users, use `build/engine/internpath_dsa.exe` instead of `build/engine/Release/internpath_dsa.exe`.

Check `http://127.0.0.1:8000/health` in your browser. Interactive API documentation is at `http://127.0.0.1:8000/docs`.

## 3. Start React (second terminal)

```bash
cd apps/web
npm install
npm run dev
```

Open the localhost URL shown in the terminal (usually `http://localhost:5173`). Modify the skill-level selectors and choose **Recalculate**. The resulting coverage is computed by C++, not by the browser or an LLM.

## 4. Run API tests (from repo root, using your virtual environment)

```bash
python -m pytest services/api/tests -v
```

## What to do if it fails

- `cmake not recognized`: install CMake and reopen the terminal.
- `No CMAKE_CXX_COMPILER`: install Visual Studio Build Tools with C++ workload or a supported GCC/Clang toolchain.
- `Engine executable not found`: compile C++ and, on MSVC, set `INTERNPATH_DSA_BIN` to the Release `.exe` path.
- `No module named fastapi`: activate your virtual environment and install requirements.
- Browser shows `Failed to fetch`: FastAPI must be running on port 8000; Vite proxies `/v1` to that address.
- `npm is not recognized`: install Node.js and reopen the terminal.

## Future target architecture

React/TypeScript → FastAPI/Pydantic → Python career services and constrained agent → C++20 algorithm engine and PostgreSQL. The C++ command-line argument transport is a temporary bridge for this first integration test; later replace it with a versioned JSON-in/JSON-out protocol or a tested direct binding.

Read `docs/NEXT_STEPS.md`, `docs/ARCHITECTURE.md`, and `docs/INNOVAX_DATES.md` before expanding the project.
