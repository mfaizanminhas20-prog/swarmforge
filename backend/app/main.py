"""
FastAPI application for SWARMFORGE mission orchestration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from app.algorithms.cpm import CPM
from app.algorithms.fcfs import FCFSScheduler
from app.algorithms.models import Agent, Schedule, Task
from app.algorithms.scheduler import GreedyScheduler
from app.decomposer import decompose
from app.events import ConnectionManager
from app.exceptions import Conflict, NotFound, ValidationError
from app.executor import Engine
from app.state import MissionState, SimClock

# Load environment configuration
load_dotenv()

logger = logging.getLogger("swarmforge")
logging.basicConfig(level=logging.INFO)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# FastAPI Initialization & CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SWARMFORGE API",
    description="Dynamic Multi-Agent Task Allocation, Scheduling & Failure-Recovery System",
    version="1.0.0",
)

# CORS configuration: default to "*" per repo invariants
cors_env = os.getenv("CORS_ORIGINS", "*")
if cors_env.strip() == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global State & Connection Manager
# ---------------------------------------------------------------------------

manager = ConnectionManager()
current_engine: Optional[Engine] = None
task_start_times: Dict[str, float] = {}
task_end_times: Dict[str, float] = {}


async def on_engine_event(event: Dict[str, Any]) -> None:
    """Subscriber for engine events: updates task execution times and broadcasts to WebSockets."""
    ev_type = event.get("type")
    t_val = event.get("t")
    tid = event.get("task_id")

    if ev_type == "task_started" and tid is not None:
        if t_val is not None:
            task_start_times[tid] = float(t_val)
        if current_engine and tid in current_engine.state.tasks:
            task = current_engine.state.tasks[tid]
            if t_val is not None:
                setattr(task, "start_t", float(t_val))
            setattr(task, "agent_id", event.get("agent_id"))
    elif ev_type == "task_done" and tid is not None:
        if t_val is not None:
            task_end_times[tid] = float(t_val)
        if current_engine and tid in current_engine.state.tasks:
            task = current_engine.state.tasks[tid]
            if t_val is not None:
                setattr(task, "end_t", float(t_val))

    await manager.broadcast(event)


def get_snapshot(engine: Optional[Engine]) -> Dict[str, Any]:
    """
    Generate the full snapshot representing current mission execution state.
    Used by GET /state and sent on WebSocket connection.
    """
    if engine is None:
        return {
            "type": "snapshot",
            "mission": None,
            "status": "idle",
            "failed_reason": None,
            "t": 0.0,
            "sim_time": 0.0,
            "seq": 0,
            "last_seq": 0,
            "agents": [],
            "tasks": [],
            "current_schedule": None,
            "critical_path": [],
            "cpm_details": {},
            "events": [],
            "event_log": [],
        }

    t = round(engine.clock.now(), 2)
    last_seq = engine._seq - 1 if engine._seq > 1 else 0

    # Build agent list
    agents: List[Dict[str, Any]] = []
    for aid, agent in engine.state.agents.items():
        st = "dead" if aid in engine.state.dead else engine.agent_status.get(aid, "idle")
        agents.append(
            {
                "id": agent.id,
                "name": agent.name,
                "skills": list(agent.skills),
                "speed": agent.speed,
                "cost_per_unit": agent.cost_per_unit,
                "status": st,
                "current_task": agent.current_task,
                "tasks_done": engine.tasks_done.get(aid, 0),
            }
        )

    # Build task assignment lookup
    asgn_map: Dict[str, Any] = {}
    if engine.state.current_schedule and hasattr(engine.state.current_schedule, "assignments"):
        for asgn in engine.state.current_schedule.assignments:
            asgn_map[asgn.task_id] = asgn

    # Build task list
    tasks: List[Dict[str, Any]] = []
    for tid, task in engine.state.tasks.items():
        asgn = asgn_map.get(tid)
        assigned_agent = (
            engine.state.running.get(tid)
            or getattr(task, "agent_id", None)
            or (asgn.agent_id if asgn else None)
        )
        start_t = (
            task_start_times.get(tid)
            or getattr(task, "start_t", None)
            or (asgn.start_time if asgn else None)
        )
        end_t = (
            task_end_times.get(tid)
            or getattr(task, "end_t", None)
            or (asgn.end_time if asgn else None)
        )

        tasks.append(
            {
                "id": task.id,
                "name": task.name,
                "required_skill": task.required_skill,
                "deps": list(task.deps),
                "priority": task.priority,
                "status": task.status,
                "agent_id": assigned_agent,
                "start_t": start_t,
                "end_t": end_t,
            }
        )

    # Compute CPM critical path & details
    tasks_list = list(engine.state.tasks.values())
    if tasks_list:
        try:
            cpm = CPM(tasks_list)
            critical_path = cpm.compute_critical_path()
            cpm_details = cpm.get_details()
        except Exception:
            critical_path = []
            cpm_details = {}
    else:
        critical_path = []
        cpm_details = {}

    recent_events = engine.state.event_log[-200:]

    return {
        "type": "snapshot",
        "mission": engine.state.mission,
        "status": engine.state.status,
        "failed_reason": engine.state.failed_reason,
        "t": t,
        "sim_time": t,
        "seq": last_seq,
        "last_seq": last_seq,
        "agents": agents,
        "tasks": tasks,
        "current_schedule": (
            engine.state.current_schedule.to_dict()
            if engine.state.current_schedule and hasattr(engine.state.current_schedule, "to_dict")
            else engine.state.current_schedule
        ),
        "critical_path": critical_path,
        "cpm_details": cpm_details,
        "events": recent_events,
        "event_log": recent_events,
    }


def _load_fixture_json(filename: str) -> Any:
    file_path = FIXTURES_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Fixture file '{filename}' not found")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission: Optional[str] = None
    fixture: Optional[Literal["demo_wide", "rest_api"]] = None
    use_gemini: bool = False


class EventRequestBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["agent_failure", "budget_cut", "task_added"]
    agent_id: Optional[str] = None
    new_budget: Optional[float] = None
    task: Optional[Union[Dict[str, Any], Task]] = None


class SpeedRequestBody(BaseModel):
    multiplier: float = Field(..., ge=0.25, le=4.0)


# ---------------------------------------------------------------------------
# REST Routes
# ---------------------------------------------------------------------------


@app.post("/mission")
async def create_mission(req: MissionCreateRequest) -> Dict[str, Any]:
    """
    Create and initialize a new mission.
    Cleanly cancels any previously active mission's workers.
    """
    global current_engine, task_start_times, task_end_times

    # Cleanly cancel prior mission execution if active
    if current_engine is not None:
        await current_engine.finish()
        current_engine = None

    task_start_times.clear()
    task_end_times.clear()

    if req.use_gemini:
        if req.fixture == "rest_api":
            agents_data = _load_fixture_json("rest_api.json")["agents"]
            agents_dict = {a["id"]: Agent.from_dict(a) for a in agents_data}
            mission_name = req.mission or "Build and validate a secure REST API"
        else:
            agents_data = _load_fixture_json("agents_default.json")
            agents_list = agents_data if isinstance(agents_data, list) else agents_data.get("agents", [])
            agents_dict = {a["id"]: Agent.from_dict(a) for a in agents_list}
            mission_name = req.mission or "Build and launch a SaaS MVP"

        tasks, source = await decompose(mission=mission_name, agents=list(agents_dict.values()))
        tasks_dict = {t.id: t for t in tasks}
    else:
        if req.fixture is None:
            raise HTTPException(
                status_code=422,
                detail="fixture must be specified when use_gemini is false",
            )

        # Load fixture data
        if req.fixture == "rest_api":
            data = _load_fixture_json("rest_api.json")
            tasks_dict = {t["id"]: Task.from_dict(t) for t in data["tasks"]}
            agents_dict = {a["id"]: Agent.from_dict(a) for a in data["agents"]}
            mission_name = req.mission or data.get("mission", "Build and validate a secure REST API")
            source = "rest_api"
        elif req.fixture == "demo_wide":
            data = _load_fixture_json("demo_wide.json")
            agents_data = _load_fixture_json("agents_default.json")
            tasks_dict = {t["id"]: Task.from_dict(t) for t in data["tasks"]}
            agents_list = agents_data if isinstance(agents_data, list) else agents_data.get("agents", [])
            agents_dict = {a["id"]: Agent.from_dict(a) for a in agents_list}
            mission_name = req.mission or data.get("mission", "Build and launch a SaaS MVP")
            source = "demo_wide"
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported fixture: {req.fixture}")

    mission_id = f"mission-{uuid.uuid4().hex[:6]}"
    state = MissionState(
        mission_id=mission_id,
        mission=mission_name,
        tasks=tasks_dict,
        agents=agents_dict,
    )
    engine = Engine(state=state)
    engine.fixture_name = source
    engine.add_event_listener(on_engine_event)

    schedule = await engine.create_initial_plan()
    tasks_list = list(state.tasks.values())
    cpm = CPM(tasks_list)
    critical_path = cpm.compute_critical_path()
    cpm_details = cpm.get_details()

    current_engine = engine

    return {
        "mission_id": mission_id,
        "mission": mission_name,
        "tasks": [t.to_dict() for t in state.tasks.values()],
        "agents": [a.to_dict() for a in state.agents.values()],
        "schedule": schedule.to_dict(),
        "critical_path": critical_path,
        "cpm_details": cpm_details,
        "makespan": schedule.makespan,
        "total_cost": schedule.total_cost,
        "source": source,
    }


@app.post("/mission/start")
async def start_mission() -> Dict[str, Any]:
    """Start execution of the current mission."""
    global current_engine
    if current_engine is None:
        raise HTTPException(status_code=404, detail="No mission found")

    if current_engine.state.status == "running":
        raise HTTPException(status_code=409, detail="Mission is already running")

    if current_engine.state.status in ("done", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start mission in '{current_engine.state.status}' state",
        )

    await current_engine.start()
    return {
        "status": "running",
        "mission_id": current_engine.state.mission_id,
        "message": "Mission started",
    }


@app.post("/event")
async def post_event(req: EventRequestBody) -> Dict[str, Any]:
    """Submit a dynamic runtime event (agent_failure, budget_cut, task_added)."""
    global current_engine
    if current_engine is None:
        raise HTTPException(status_code=404, detail="No active mission")

    payload = req.model_dump(exclude_unset=False)
    try:
        await current_engine.handle_event(payload)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Conflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"status": "ok", "event": payload}


@app.post("/speed")
async def set_speed(body: SpeedRequestBody) -> Dict[str, Any]:
    """Update execution speed multiplier between 0.25 and 4.0."""
    global current_engine
    if current_engine is None:
        raise HTTPException(status_code=404, detail="No active mission")

    try:
        await current_engine.set_speed(body.multiplier)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"multiplier": body.multiplier, "status": "ok"}


@app.get("/state")
async def get_state() -> Dict[str, Any]:
    """Return complete state snapshot."""
    return get_snapshot(current_engine)


@app.get("/report")
async def get_report() -> Dict[str, Any]:
    """Return final mission report."""
    global current_engine
    if current_engine is None:
        raise HTTPException(status_code=404, detail="No mission exists")

    state = current_engine.state
    total_time = round(current_engine.clock.now(), 2)
    actual_cost = round(state.actual_cost, 2)
    wasted_cost = round(state.wasted_cost, 2)
    tasks_completed = len(state.done)
    tasks_total = len(state.tasks)

    return {
        "mission_id": state.mission_id,
        "mission": state.mission,
        "status": state.status,
        "total_time": total_time,
        "total_cost": actual_cost,
        "actual_cost": actual_cost,
        "wasted_cost": wasted_cost,
        "tasks_completed": tasks_completed,
        "tasks_done": tasks_completed,
        "tasks_total": tasks_total,
        "failures_recovered": state.failures_recovered,
        "failed_reason": state.failed_reason,
        "event_log": list(state.event_log),
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/compare")
async def compare(
    fixture: Optional[str] = Query(default="demo_wide"),
) -> Dict[str, Any]:
    """
    Compare greedy algorithm metrics against FCFS baseline.
    Accepts ?fixture=demo_wide when no mission is active yet (per AGENTS.md invariant).
    When a mission is active, compares schedules using the mission's initial tasks
    and full initial roster (unaffected by later agent kills).
    """
    global current_engine

    if current_engine is not None and getattr(current_engine.state, "initial_tasks", None):
        target_fixture = getattr(current_engine, "fixture_name", "mission")
        init_tasks = [Task.from_dict(t.to_dict()) for t in current_engine.state.initial_tasks]
        init_agents = [
            Agent(
                id=a.id,
                name=a.name,
                skills=list(a.skills),
                speed=a.speed,
                cost_per_unit=a.cost_per_unit,
                available=True,
                current_task=None,
            )
            for a in current_engine.state.initial_agents
        ]
    else:
        target_fixture = fixture or "demo_wide"
        if target_fixture == "rest_api":
            data = _load_fixture_json("rest_api.json")
            init_tasks = [Task.from_dict(t) for t in data["tasks"]]
            init_agents = [Agent.from_dict(a) for a in data["agents"]]
        elif target_fixture == "demo_wide":
            data = _load_fixture_json("demo_wide.json")
            agents_data = _load_fixture_json("agents_default.json")
            init_tasks = [Task.from_dict(t) for t in data["tasks"]]
            agents_list = (
                agents_data if isinstance(agents_data, list) else agents_data.get("agents", [])
            )
            init_agents = [Agent.from_dict(a) for a in agents_list]
        else:
            raise HTTPException(status_code=404, detail=f"Fixture {target_fixture} not found")

    # Run GreedyScheduler
    greedy_scheduler = GreedyScheduler()
    greedy_tasks = [Task.from_dict(t.to_dict()) for t in init_tasks]
    greedy_agents = [Agent.from_dict(a.to_dict()) for a in init_agents]
    greedy_sched = greedy_scheduler.greedy_schedule(greedy_tasks, greedy_agents)

    # Run FCFSScheduler
    fcfs_scheduler = FCFSScheduler()
    fcfs_tasks = [Task.from_dict(t.to_dict()) for t in init_tasks]
    fcfs_agents = [Agent.from_dict(a.to_dict()) for a in init_agents]
    fcfs_sched = fcfs_scheduler.greedy_schedule(fcfs_tasks, fcfs_agents)

    time_pct = (
        round((fcfs_sched.makespan - greedy_sched.makespan) / fcfs_sched.makespan * 100, 2)
        if fcfs_sched.makespan > 0
        else 0.0
    )
    cost_pct = (
        round((fcfs_sched.total_cost - greedy_sched.total_cost) / fcfs_sched.total_cost * 100, 2)
        if fcfs_sched.total_cost > 0
        else 0.0
    )

    return {
        "fixture": target_fixture,
        "greedy": {
            "makespan": greedy_sched.makespan,
            "total_cost": greedy_sched.total_cost,
            "assignments": [a.to_dict() for a in greedy_sched.assignments],
        },
        "fcfs": {
            "makespan": fcfs_sched.makespan,
            "total_cost": fcfs_sched.total_cost,
            "assignments": [a.to_dict() for a in fcfs_sched.assignments],
        },
        "improvement": {
            "time_pct": time_pct,
            "cost_pct": cost_pct,
        },
    }


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time mission telemetry.
    Sends full snapshot on connect, then streams every engine event.
    """
    await manager.connect(websocket)
    snapshot = get_snapshot(current_engine)
    await websocket.send_json(snapshot)

    try:
        while True:
            # Keep socket alive and await incoming ping/text or disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
