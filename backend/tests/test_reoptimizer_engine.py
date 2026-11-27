"""
Unit and integration tests for Engine re-optimizer and dynamic event handling (Prompt 5).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List
import pytest

from app.algorithms.models import Agent, Task
from app.exceptions import Conflict, NotFound, ValidationError
from app.executor import Engine
from app.state import MissionState, SimClock


@pytest.fixture
def rest_api_data() -> dict:
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "rest_api.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def demo_wide_data() -> dict:
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "demo_wide.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def default_agents_data() -> list:
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "agents_default.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
@pytest.mark.parametrize("kill_delay", [0.01, 0.06, 0.12])
async def test_rest_api_with_backup_agent_kill_a2_at_several_times(
    rest_api_data: dict, kill_delay: float
) -> None:
    """
    rest_api fixture plus a 4th backup agent:
    Kill a2 at several times -> 8/8 done, no duplicate completions, dependency order intact.
    """
    data = dict(rest_api_data)
    # Add a 4th backup agent with skills covering backend, database, security, testing
    backup_agent = {
        "id": "a4",
        "name": "Fullstack Backup Agent",
        "skills": ["backend", "database", "security", "testing"],
        "speed": 1.1,
        "cost_per_unit": 2.2,
        "available": True,
        "current_task": None,
    }
    data["agents"] = list(data["agents"]) + [backup_agent]

    clock = SimClock(base_delay=0.01)
    engine = Engine.from_dict(data, clock=clock, tick_duration=0.01)

    await engine.start()
    await asyncio.sleep(kill_delay)

    # Kill a2
    await engine.handle_event({"type": "agent_failure", "agent_id": "a2"})

    assert engine.agent_status["a2"] == "dead"
    assert "a2" in engine.state.dead

    # Await mission completion
    await engine.wait_until_done(timeout=5.0)

    # 1. 8/8 done
    assert engine.state.status == "done"
    assert len(engine.state.done) == 8
    assert engine.state.done == {"t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"}

    event_log = engine.state.event_log

    # 2. No duplicate completions
    done_counts: Dict[str, int] = {}
    done_indices: Dict[str, int] = {}
    started_indices: Dict[str, int] = {}

    for idx, ev in enumerate(event_log):
        ev_type = ev.get("type")
        tid = ev.get("task_id")
        if ev_type == "task_done" and tid:
            done_counts[tid] = done_counts.get(tid, 0) + 1
            done_indices[tid] = idx
        elif ev_type == "task_started" and tid:
            # Record first start index
            if tid not in started_indices:
                started_indices[tid] = idx

    for tid in engine.state.tasks:
        assert done_counts.get(tid) == 1, f"Task {tid} completed {done_counts.get(tid)} times"

    # 3. Dependency order intact
    for tid, task in engine.state.tasks.items():
        if not task.deps:
            continue
        start_idx = started_indices[tid]
        for dep in task.deps:
            dep_done_idx = done_indices[dep]
            assert dep_done_idx < start_idx, (
                f"Dependency {dep} finished at #{dep_done_idx} after {tid} started at #{start_idx}"
            )


@pytest.mark.asyncio
async def test_kill_only_agent_for_skill_fails_quickly_never_hangs(
    rest_api_data: dict,
) -> None:
    """
    Killing the only agent for a skill -> mission_failed within a few seconds, never a hang.
    In rest_api.json, only a3 has skill 'testing'. Killing a3 makes t7 unassignable.
    """
    clock = SimClock(base_delay=0.01)
    engine = Engine.from_dict(rest_api_data, clock=clock, tick_duration=0.01)

    start_time = asyncio.get_event_loop().time()
    await engine.start()
    await asyncio.sleep(0.04)

    # Kill a3 (the only tester)
    await engine.handle_event({"type": "agent_failure", "agent_id": "a3"})

    # Wait for completion (must fail cleanly and quickly)
    await engine.wait_until_done(timeout=3.0)
    elapsed = asyncio.get_event_loop().time() - start_time

    assert elapsed < 3.0, f"Engine took {elapsed:.2f}s, expected fast failure"
    assert engine.state.status == "failed"
    assert "t7" in (engine.state.failed_reason or "")

    failed_events = [ev for ev in engine.state.event_log if ev.get("type") == "mission_failed"]
    assert len(failed_events) >= 1
    assert "t7" in failed_events[0].get("reason", "")


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id_to_kill", ["a1", "a2", "a3", "a4", "a5"])
async def test_agents_default_killing_any_single_agent_succeeds(
    demo_wide_data: dict, default_agents_data: list, agent_id_to_kill: str
) -> None:
    """
    With agents_default.json and a mission using all skills (demo_wide.json):
    Killing ANY single agent at any time -> mission completes.
    """
    data = {
        "mission": demo_wide_data["mission"],
        "tasks": demo_wide_data["tasks"],
        "agents": default_agents_data,
    }

    clock = SimClock(base_delay=0.01)
    engine = Engine.from_dict(data, clock=clock, tick_duration=0.01)

    await engine.start()
    await asyncio.sleep(0.05)

    # Kill the designated agent
    await engine.handle_event({"type": "agent_failure", "agent_id": agent_id_to_kill})

    assert engine.agent_status[agent_id_to_kill] == "dead"
    assert agent_id_to_kill in engine.state.dead

    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert len(engine.state.done) == 12
    assert engine.state.failures_recovered >= 1


@pytest.mark.asyncio
async def test_killing_unknown_or_dead_agent_raises_error_and_changes_nothing(
    rest_api_data: dict,
) -> None:
    """
    Killing an unknown or dead agent raises the right error and changes nothing.
    Also validates calling agent_failure when no mission is running.
    """
    data = dict(rest_api_data)
    backup_agent = {
        "id": "a4",
        "name": "Backup Agent",
        "skills": ["backend", "database", "security", "testing"],
        "speed": 1.0,
        "cost_per_unit": 2.0,
        "available": True,
        "current_task": None,
    }
    data["agents"] = list(data["agents"]) + [backup_agent]

    clock = SimClock(base_delay=0.01)
    engine = Engine.from_dict(data, clock=clock, tick_duration=0.01)

    # 1. Before mission running -> Conflict
    with pytest.raises(Conflict, match="No mission running"):
        await engine.handle_event({"type": "agent_failure", "agent_id": "a1"})

    await engine.start()

    # Capture baseline state
    initial_dead = set(engine.state.dead)
    initial_status = dict(engine.agent_status)

    # 2. Unknown agent -> NotFound
    with pytest.raises(NotFound, match="not found"):
        await engine.handle_event({"type": "agent_failure", "agent_id": "unknown_agent_999"})

    assert engine.state.dead == initial_dead
    assert engine.agent_status == initial_status
    assert engine.state.status == "running"

    # 3. Kill valid agent a1 -> succeeds
    await engine.handle_event({"type": "agent_failure", "agent_id": "a1"})
    assert "a1" in engine.state.dead
    assert engine.agent_status["a1"] == "dead"

    # 4. Kill already dead agent a1 -> Conflict
    with pytest.raises(Conflict, match="already dead"):
        await engine.handle_event({"type": "agent_failure", "agent_id": "a1"})

    # State still consistent
    assert "a1" in engine.state.dead
    assert engine.agent_status["a1"] == "dead"

    await engine.finish()


@pytest.mark.asyncio
async def test_budget_cut_disables_agent_running_task_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    budget_cut that disables an agent mid-run:
    Its running task still finishes; remaining tasks go to other agents.
    """
    from app.algorithms.models import Schedule, ScheduledTask

    # Two tasks requiring 'backend'
    tasks = {
        "t1": Task(
            id="t1",
            name="First Backend Task",
            required_skill="backend",
            est_time=4.0,
            est_cost=20.0,
            deps=[],
        ),
        "t2": Task(
            id="t2",
            name="Second Backend Task",
            required_skill="backend",
            est_time=4.0,
            est_cost=8.0,
            deps=["t1"],
        ),
    }

    # a_expensive (cost 5.0), a_affordable (cost 2.0)
    agents = {
        "a_expensive": Agent(
            id="a_expensive",
            name="Expensive Agent",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=5.0,
        ),
        "a_affordable": Agent(
            id="a_affordable",
            name="Affordable Agent",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=2.0,
        ),
    }

    state = MissionState(mission_id="m_budget", mission="Budget Cut Test", tasks=tasks, agents=agents)
    clock = SimClock(base_delay=0.01)
    engine = Engine(state=state, clock=clock, tick_duration=0.01)

    initial_schedule = Schedule(
        assignments=[
            ScheduledTask(task_id="t1", agent_id="a_expensive", start_time=0.0, end_time=4.0),
            ScheduledTask(task_id="t2", agent_id="a_expensive", start_time=4.0, end_time=8.0),
        ],
        makespan=8.0,
        total_cost=40.0,
    )

    await engine.start(schedule=initial_schedule)
    await asyncio.sleep(0.03)

    # Verify a_expensive is running t1
    assert engine.state.running.get("t1") == "a_expensive"

    # Issue budget cut with new_budget = 3.0 (caps cost at 3.0)
    # a_expensive has cost 5.0 > 3.0, so it will be disabled
    await engine.handle_event({"type": "budget_cut", "new_budget": 3.0})

    # a_expensive is disabled (available=False), but NOT dead!
    assert not engine.state.agents["a_expensive"].available
    assert "a_expensive" not in engine.state.dead

    # Await mission completion
    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert engine.state.done == {"t1", "t2"}

    # Running task t1 finished on a_expensive
    assert engine.tasks_done["a_expensive"] == 1

    # Remaining task t2 went to a_affordable
    assert engine.tasks_done["a_affordable"] == 1


@pytest.mark.asyncio
async def test_task_added_validations_and_replan() -> None:
    """
    task_added event:
    - Validate duplicate id -> Conflict
    - Validate unknown dependency ids -> ValidationError
    - Validate cycle (DAG.topological_sort) -> ValidationError
    - Valid task added mid-run -> replans and finishes with all tasks done
    """
    tasks = {
        "t1": Task(id="t1", name="Task 1", required_skill="backend", est_time=2.0, est_cost=2.0, deps=[]),
        "t2": Task(id="t2", name="Task 2", required_skill="backend", est_time=2.0, est_cost=2.0, deps=["t1"]),
    }
    agents = {
        "a1": Agent(id="a1", name="Agent 1", skills=["backend"], speed=1.0, cost_per_unit=1.0),
    }
    state = MissionState(mission_id="m_add", mission="Task Add Test", tasks=tasks, agents=agents)
    clock = SimClock(base_delay=0.01)
    engine = Engine(state=state, clock=clock, tick_duration=0.01)

    await engine.start()
    await asyncio.sleep(0.01)

    # 1. Duplicate ID -> Conflict
    with pytest.raises(Conflict, match="already exists"):
        await engine.handle_event({
            "type": "task_added",
            "task": {"id": "t1", "name": "Dup", "required_skill": "backend", "est_time": 1, "est_cost": 1},
        })

    # 2. Unknown dependency ID -> ValidationError
    with pytest.raises(ValidationError, match="Unknown dependency"):
        await engine.handle_event({
            "type": "task_added",
            "task": {
                "id": "t_unknown_dep",
                "name": "Bad Dep",
                "required_skill": "backend",
                "est_time": 1,
                "est_cost": 1,
                "deps": ["t_nonexistent"],
            },
        })

    # 3. Cycle -> ValidationError
    # Pre-introduce a task with an unresolved forward reference to simulate cycle detection
    engine.state.tasks["t_forward"] = Task(
        id="t_forward",
        name="Forward Dep",
        required_skill="backend",
        est_time=1,
        est_cost=1,
        deps=["t_cycle_new"],
    )
    with pytest.raises(ValidationError, match="Cycle detected"):
        await engine.handle_event({
            "type": "task_added",
            "task": {
                "id": "t_cycle_new",
                "name": "Cycle Task",
                "required_skill": "backend",
                "est_time": 1,
                "est_cost": 1,
                "deps": ["t_forward"],
            },
        })
    del engine.state.tasks["t_forward"]

    # 4. Valid dynamic task added mid-run
    await engine.handle_event({
        "type": "task_added",
        "task": {
            "id": "t3",
            "name": "Task 3 (Dynamic)",
            "required_skill": "backend",
            "est_time": 2.0,
            "est_cost": 2.0,
            "deps": ["t2"],
        },
    })

    # Verify replanned event was emitted with required fields
    replanned_events = [ev for ev in engine.state.event_log if ev.get("type") == "replanned"]
    assert len(replanned_events) >= 1
    rep_ev = replanned_events[-1]
    assert "schedule" in rep_ev
    assert "task_status" in rep_ev
    assert "reassigned_task_ids" in rep_ev
    assert "total_cost" in rep_ev
    assert "projected_finish_t" in rep_ev
    assert "cpm_details" in rep_ev

    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert engine.state.done == {"t1", "t2", "t3"}
