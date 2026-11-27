"""
Unit and integration tests for Engine in backend/app/executor.py.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List
import pytest

from app.algorithms.models import Agent, Task
from app.executor import Engine
from app.state import MissionState, SimClock


@pytest.mark.asyncio
async def test_rest_api_full_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test rest_api.json fixture execution:
    - All 8 tasks finish.
    - In event log, every task_started comes after its dependencies' task_done.
    - No task completes twice.
    """
    monkeypatch.setenv("SWARM_BASE_DELAY", "0.01")
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "fixtures", "rest_api.json"
    )

    clock = SimClock(base_delay=0.01)
    engine = Engine.from_fixture(
        fixture_path=fixture_path,
        clock=clock,
        tick_duration=0.01,
    )

    await engine.start()
    await engine.wait_until_done(timeout=5.0)

    # All 8 tasks finish
    assert engine.state.status == "done"
    assert len(engine.state.done) == 8
    assert engine.state.done == {"t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"}

    event_log = engine.state.event_log
    assert len(event_log) > 0

    # Count task_done events per task: no task completes twice
    done_events: Dict[str, int] = {}
    done_indices: Dict[str, int] = {}
    started_indices: Dict[str, int] = {}

    for idx, ev in enumerate(event_log):
        ev_type = ev.get("type")
        tid = ev.get("task_id")
        if ev_type == "task_done" and tid is not None:
            done_events[tid] = done_events.get(tid, 0) + 1
            done_indices[tid] = idx
        elif ev_type == "task_started" and tid is not None:
            started_indices[tid] = idx

    for tid in engine.state.tasks:
        assert done_events.get(tid) == 1, f"Task {tid} completed {done_events.get(tid)} times"

    # In the event log every task_started comes after its dependencies' task_done
    for tid, task in engine.state.tasks.items():
        if not task.deps:
            continue
        task_start_idx = started_indices[tid]
        for dep in task.deps:
            dep_done_idx = done_indices[dep]
            assert (
                dep_done_idx < task_start_idx
            ), f"Dependency {dep} finished at index {dep_done_idx} after {tid} started at {task_start_idx}"

    # Plan payload verification
    plan_events = [ev for ev in event_log if ev.get("type") == "plan_created"]
    assert len(plan_events) >= 1
    p_ev = plan_events[0]
    assert "schedule" in p_ev
    assert "makespan" in p_ev
    assert "total_cost" in p_ev
    assert "cpm_details" in p_ev
    assert len(p_ev["cpm_details"]) == 8

    # Mission done event verification
    mission_done_events = [ev for ev in event_log if ev.get("type") == "mission_done"]
    assert len(mission_done_events) == 1
    m_ev = mission_done_events[0]
    assert m_ev["actual_cost"] > 0
    assert m_ev["wasted_cost"] == 0.0
    assert m_ev["failures_recovered"] == 0
    assert m_ev["total_time"] > 0

    # Agent properties verification
    for aid, agent in engine.state.agents.items():
        assert agent.current_task is None
        assert engine.agent_status[aid] == "idle"
        assert getattr(agent, "status") == "idle"

    assert sum(engine.tasks_done.values()) == 8


@pytest.mark.asyncio
async def test_changing_multiplier_mid_task_shortens_wall_time() -> None:
    """
    Verify that increasing speed multiplier mid-task shortens the remaining wall time.
    """
    # Run 1: Baseline at multiplier=1.0
    tasks_1 = {
        "t1": Task(
            id="t1",
            name="Long Task",
            required_skill="backend",
            est_time=10.0,
            est_cost=10.0,
            deps=[],
        )
    }
    agents_1 = {
        "a1": Agent(
            id="a1",
            name="Worker 1",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=1.0,
        )
    }
    state_1 = MissionState(mission_id="m1", mission="Test Baseline", tasks=tasks_1, agents=agents_1)
    clock_1 = SimClock(multiplier=1.0, base_delay=0.05)
    engine_1 = Engine(state=state_1, clock=clock_1, tick_duration=0.05)

    start_wall_1 = time.monotonic()
    await engine_1.start()
    await engine_1.wait_until_done(timeout=5.0)
    duration_1 = time.monotonic() - start_wall_1

    # Run 2: Mid-task speedup to multiplier=4.0
    tasks_2 = {
        "t1": Task(
            id="t1",
            name="Long Task",
            required_skill="backend",
            est_time=10.0,
            est_cost=10.0,
            deps=[],
        )
    }
    agents_2 = {
        "a1": Agent(
            id="a1",
            name="Worker 1",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=1.0,
        )
    }
    state_2 = MissionState(mission_id="m2", mission="Test Speedup", tasks=tasks_2, agents=agents_2)
    clock_2 = SimClock(multiplier=1.0, base_delay=0.05)
    engine_2 = Engine(state=state_2, clock=clock_2, tick_duration=0.05)

    start_wall_2 = time.monotonic()
    await engine_2.start()

    # Wait for 1 tick (~0.05s) then speed up to 4x
    await asyncio.sleep(0.06)
    await engine_2.set_speed(4.0)

    await engine_2.wait_until_done(timeout=5.0)
    duration_2 = time.monotonic() - start_wall_2

    # Run 2 should be noticeably faster than Run 1
    assert duration_2 < duration_1 * 0.75, (
        f"Speedup duration {duration_2:.3f}s was not significantly shorter "
        f"than baseline duration {duration_1:.3f}s"
    )


@pytest.mark.asyncio
async def test_set_speed_bounds_validation() -> None:
    """Verify set_speed validates 0.25 <= multiplier <= 4."""
    state = MissionState(
        mission_id="m_val",
        mission="Test Validation",
        tasks={"t1": Task(id="t1", name="Task 1", required_skill="dev", est_time=1.0, est_cost=1.0)},
        agents={"a1": Agent(id="a1", name="Agent 1", skills=["dev"])},
    )
    engine = Engine(state=state, tick_duration=0.05)

    # Valid bounds
    await engine.set_speed(0.25)
    assert engine.clock.multiplier == 0.25

    await engine.set_speed(4.0)
    assert engine.clock.multiplier == 4.0

    await engine.set_speed(2.5)
    assert engine.clock.multiplier == 2.5

    # Invalid lower bound
    with pytest.raises(ValueError, match="0.25 and 4.0"):
        await engine.set_speed(0.24)

    with pytest.raises(ValueError, match="0.25 and 4.0"):
        await engine.set_speed(0.0)

    # Invalid upper bound
    with pytest.raises(ValueError, match="0.25 and 4.0"):
        await engine.set_speed(4.01)

    with pytest.raises(ValueError, match="0.25 and 4.0"):
        await engine.set_speed(10.0)


@pytest.mark.asyncio
async def test_agent_failure_accounting_and_recovery() -> None:
    """
    Verify agent failure mid-task:
    - Worker is cancelled and swallowed.
    - Partial cost goes to BOTH actual_cost and wasted_cost.
    - Surviving agent takes over and mission finishes.
    """
    tasks = {
        "t1": Task(
            id="t1",
            name="Mission Task",
            required_skill="backend",
            est_time=10.0,
            est_cost=20.0,
            deps=[],
        )
    }
    agents = {
        "a1": Agent(
            id="a1",
            name="Failing Agent",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=2.0,
        ),
        "a2": Agent(
            id="a2",
            name="Backup Agent",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=3.0,
        ),
    }
    state = MissionState(mission_id="m_fail", mission="Test Failure", tasks=tasks, agents=agents)
    clock = SimClock(multiplier=1.0, base_delay=0.05)
    engine = Engine(state=state, clock=clock, tick_duration=0.05)

    await engine.start()

    # Let a1 work for a few ticks (~0.12s -> ~2-3 ticks)
    await asyncio.sleep(0.12)

    # Trigger failure on a1 mid-task
    await engine.handle_event("agent_failure", {"agent_id": "a1"})

    assert engine.agent_status["a1"] == "dead"
    assert "a1" in engine.state.dead
    assert engine.state.wasted_cost > 0.0
    assert engine.state.actual_cost >= engine.state.wasted_cost
    assert engine.state.failures_recovered == 1

    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert "t1" in engine.state.done
    assert engine.tasks_done["a2"] == 1


@pytest.mark.asyncio
async def test_executor_finish_cancels_cleanly() -> None:
    """Verify finish() cancels active workers and swallows CancelledError."""
    tasks = {
        "t1": Task(
            id="t1",
            name="Endless Task",
            required_skill="backend",
            est_time=1000.0,
            est_cost=1000.0,
            deps=[],
        )
    }
    agents = {
        "a1": Agent(
            id="a1",
            name="Worker",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=1.0,
        )
    }
    state = MissionState(mission_id="m_finish", mission="Test Finish", tasks=tasks, agents=agents)
    engine = Engine(state=state, tick_duration=0.05)

    await engine.start()
    await asyncio.sleep(0.08)

    # Cancel via finish
    await engine.finish()

    assert engine.state.status == "done"
    assert engine.done_event.is_set()


@pytest.mark.asyncio
async def test_worker_loop_does_not_prematurely_pop_blocked_task() -> None:
    """
    Verify worker does not pop a queued task whose dependencies are unmet.
    If queued task 1 depends on unfinished task 2, but queued task 2 is ready,
    worker skips task 1 and picks task 2 without blocking.
    """
    tasks = {
        "t_dep": Task(
            id="t_dep",
            name="Dependent Task",
            required_skill="backend",
            est_time=1.0,
            est_cost=1.0,
            deps=["t_prep"],
        ),
        "t_prep": Task(
            id="t_prep",
            name="Prerequisite Task",
            required_skill="backend",
            est_time=1.0,
            est_cost=1.0,
            deps=[],
        ),
    }
    agents = {
        "a1": Agent(
            id="a1",
            name="Solo Worker",
            skills=["backend"],
            speed=1.0,
            cost_per_unit=1.0,
        )
    }
    state = MissionState(mission_id="m_order", mission="Test Order", tasks=tasks, agents=agents)
    clock = SimClock(base_delay=0.01)
    engine = Engine(state=state, clock=clock, tick_duration=0.01)

    # Manually configure queue in reverse order: t_dep first, then t_prep
    engine._agent_queues["a1"] = ["t_dep", "t_prep"]

    # Start without overwriting schedule
    async with engine._lock:
        engine.state.status = "running"
        engine._worker_tasks["a1"] = asyncio.create_task(engine._worker_loop("a1"))
        for ev in engine._wake_events.values():
            ev.set()

    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert engine.state.done == {"t_dep", "t_prep"}

    # t_prep must have completed before t_dep started
    event_log = engine.state.event_log
    prep_done_idx = next(
        i for i, ev in enumerate(event_log) if ev.get("type") == "task_done" and ev.get("task_id") == "t_prep"
    )
    dep_start_idx = next(
        i for i, ev in enumerate(event_log) if ev.get("type") == "task_started" and ev.get("task_id") == "t_dep"
    )
    assert prep_done_idx < dep_start_idx


@pytest.mark.asyncio
async def test_demo_wide_fixture_execution() -> None:
    """Verify demo_wide.json (12 tasks, 5 default agents) runs to completion."""
    fixture_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
    demo_path = os.path.join(fixture_dir, "demo_wide.json")
    agents_path = os.path.join(fixture_dir, "agents_default.json")

    import json
    with open(demo_path, "r", encoding="utf-8") as f:
        demo_data = json.load(f)
    with open(agents_path, "r", encoding="utf-8") as f:
        agents_data = json.load(f)

    tasks = {t["id"]: Task.from_dict(t) for t in demo_data["tasks"]}
    raw_agents = agents_data["agents"] if isinstance(agents_data, dict) else agents_data
    agents = {a["id"]: Agent.from_dict(a) for a in raw_agents}

    state = MissionState(mission_id="demo_wide_run", mission=demo_data["mission"], tasks=tasks, agents=agents)
    clock = SimClock(base_delay=0.01)
    engine = Engine(state=state, clock=clock, tick_duration=0.01)

    await engine.start()
    await engine.wait_until_done(timeout=5.0)

    assert engine.state.status == "done"
    assert len(engine.state.done) == 12
    assert engine.state.actual_cost > 0
    assert engine.state.wasted_cost == 0.0

