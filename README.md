<div align="center">
  
# 🚀 SWARMFORGE
### A Dynamic Multi-Agent Task Allocation, Scheduling & Failure-Recovery System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20React%20Flow-61DAFB.svg)](https://reactjs.org/)
[![Tests](https://img.shields.io/badge/Tests-83%20Passed-brightgreen.svg)]()
[![Course](https://img.shields.io/badge/Course-Design%20and%20Analysis%20of%20Algorithms-green.svg)]()

*SWARMFORGE is a domain-agnostic mission orchestrator. It breaks complex objectives into smaller tasks, builds a dependency DAG, assigns tasks to the best-suited AI agents, and dynamically re-plans in real-time when an agent crashes, budgets change, or new tasks are introduced.*

</div>

---

## 🧠 Core Idea

Convert a complex objective into a Directed Acyclic Graph (DAG), assign tasks to suitable AI agents, execute independent work in parallel, and **dynamically rebuild the schedule** when agents fail or execution constraints shift.

- **Domain-Agnostic**: Understands tasks, dependencies, and agent capabilities. Uses **Gemini 3.8 Flash** (`google-genai` SDK) to dynamically decompose natural language mission objectives into structured DAGs.
- **Critical Path Method (CPM)**: Computes Early Start ($ES$), Early Finish ($EF$), Late Start ($LS$), Late Finish ($LF$), and total float to determine the critical path governing mission completion.
- **Greedy Scheduler**: Optimized load-balancing algorithm factoring in agent skills, speed, and cost efficiency while enforcing dependency sequencing.
- **Fault-Tolerant Dynamic Recovery**: Self-healing orchestration that isolates failed agents, preserves completed work, accounts for wasted cost, and instantly replans pending work among surviving agents.
- **Algorithm Arena**: Side-by-side benchmark comparison of `GreedyScheduler` against a baseline First-Come-First-Serve (`FCFSScheduler`) algorithm.

---

## 🛠️ Quickstart & Run Instructions

### 1. Environment Setup
Create and activate a Python virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
Install all backend dependencies:
```bash
pip install -r backend/requirements.txt
```

Installed packages include:
- `fastapi` & `uvicorn[standard]`: High-performance ASGI web framework and server
- `python-dotenv`: Environment variable management
- `google-genai`: Official Google Gemini SDK for LLM mission decomposition
- `pytest` & `pytest-asyncio`: Async test suite execution
- `httpx`: Async HTTP client for benchmarking and testing
- `websockets`: Real-time WebSocket streaming client
- `jsonschema`: Schema validation against frozen contracts

### 3. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
*(On Windows PowerShell: `Copy-Item .env.example .env`)*

Configure your environment in `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
SWARM_BASE_DELAY=0.5
SWARM_TICK_DURATION=0.1
CORS_ORIGINS=*
```
> **Security Note**: Never commit `.env` to source control. It is strictly ignored via `.gitignore`.

### 4. Run the Backend API Server
Start the FastAPI server from the `backend/` directory:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://localhost:8000`
- Interactive Swagger Docs: `http://localhost:8000/docs`
- WebSocket Telemetry: `ws://localhost:8000/ws`

---

## 🧪 Running Tests & Benchmarks

### 1. Run the Full Test Suite
Execute the entire test suite across all modules:
```bash
pytest
```
*Expected result: 83 passed tests across algorithms, state engine, concurrency, API endpoints, LLM integration, and recovery fuzzing.*

### 2. Run the Fuzz Recovery Test Suite
Run 200 random missions through single-agent failure recovery and 30 random missions through dual-agent failure recovery:
```bash
pytest tests/test_fuzz_recovery.py
```
This suite verifies:
- Scheduler invariants on 200 randomly generated DAGs before execution.
- 100% mission completion under mid-execution single agent failure.
- Zero duplicate task completions and strict dependency sequence ordering.
- A dead agent never initiates or completes any task after failure.
- Clean resolution without hanging (enforced 5-second timeout).

### 3. Run the End-to-End Demonstration Script
Execute the standalone E2E benchmark script (communicating via HTTP REST and WebSockets):
```bash
python scripts/e2e_demo.py
```
- Runs 10 consecutive mission lifecycles on the `demo_wide` fixture.
- Kills an agent after exactly 3 tasks complete, asserting that a `replanned` event arrives and `mission_done` follows.
- Prints a readable, timestamped event timeline for every run.
- Reports final pass rate and metrics across all 10 iterations.

---

## 📁 Repository Structure

```text
swarmforge/
├── schemas/                       # Frozen JSON schema contracts
│   ├── task.schema.json
│   ├── agent.schema.json
│   └── event.schema.json
├── backend/
│   ├── app/
│   │   ├── algorithms/            # Graph DAG, CPM, GreedyScheduler, FCFS, ReOptimizer
│   │   ├── decomposer.py          # Gemini 3.8 Flash LLM task decomposer
│   │   ├── events.py              # WebSocket connection manager & event broadcaster
│   │   ├── exceptions.py          # Domain error hierarchy (NotFound, Conflict, ValidationError)
│   │   ├── executor.py            # Async multi-agent execution engine & recovery loop
│   │   ├── main.py                # FastAPI REST & WebSocket endpoints
│   │   └── state.py               # MissionState & SimClock simulation models
│   ├── fixtures/
│   │   ├── agents_default.json    # Standard 5-agent fault-tolerant roster
│   │   ├── demo_wide.json         # 12-task parallel SaaS fixture
│   │   └── rest_api.json          # 8-task REST API build fixture
│   ├── tests/                     # Unit and integration test suites
│   ├── pytest.ini                 # Backend pytest configuration
│   └── requirements.txt           # Python package requirements
├── docs/
│   ├── API.md                     # Comprehensive REST & WebSocket API specification
│   ├── FRONTEND_NOTES.md          # Frontend integration guide for Hassan
│   └── ARENA_NOTES.md             # Algorithm Arena guide for Huzaifa
├── scripts/
│   ├── e2e_demo.py                # 10-iteration E2E benchmark & timeline runner
│   └── live_gemini_check.py       # Live Gemini API decomposition verification
├── tests/
│   ├── test_arena.py              # Arena forwarding shim
│   └── test_fuzz_recovery.py      # 200-mission fuzz recovery test suite
├── AGENTS.md                      # Core repository rules and concurrency invariants
├── PROGRESS.md                    # Detailed multi-prompt implementation log
└── README.md                      # Project overview and run instructions
```

---

## 📖 Documentation
- **[docs/API.md](docs/API.md)**: Full REST route descriptions, request/response models, and verified real-world JSON payloads for all 12 WebSocket event types.
- **[docs/FRONTEND_NOTES.md](docs/FRONTEND_NOTES.md)**: UI states, node styling transitions, Gantt chart replanning, reconnection deduplication, and control labeling.
- **[docs/ARENA_NOTES.md](docs/ARENA_NOTES.md)**: Algorithm Arena integration guide detailing `GET /compare` and `GET /report` payload structures on `demo_wide`.
