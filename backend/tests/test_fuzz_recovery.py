"""
Fuzz and resilience recovery tests for SWARMFORGE (Prompt 9).

Verifies:
1. Scheduler invariants (single assignment, dependency order, no agent overlap) on 200 random missions.
2. 1-kill recovery: 200 random missions with tiny base delay and random agent kill (0-0.04s):
   - Mission completes (status == "done")
   - No task completes twice
   - Every task starts after its dependencies are done
   - Dead agent never starts or finishes a task after agent_failed
   - No hang (5s timeout)
3. 2-kill recovery:
   - Ends in mission_done or mission_failed
   - No hang (5s timeout)
   - No duplicate completions
   - No dependency violations
"""

from __future__ import annotations

import asyncio
import copy
import ctypes
import os
import random
import sys
from typing import Dict, List, Set, Tuple
import pytest

from app.algorithms.models import Agent, Schedule, Task
from app.algorithms.scheduler import GreedyScheduler
from app.executor import Engine
from app.state import MissionState, SimClock

SKILL_VOCABULARY = [
    "planning",
    "research",
    "backend",
    "database",
    "security",
    "testing",
    "design",
    "writing",
]


def make_6_agent_roster() -> List[Agent]:
    """
    Generate a 6-agent roster where every skill from the 8-skill vocabulary
    is covered by at least 2 agents.
    """
    roster_defs = [
        {"id": "a1", "name": "Agent 1", "skills": ["planning", "research", "writing"], "speed": 1.0, "cost": 2.0},
        {"id": "a2", "name": "Agent 2", "skills": ["backend", "database", "security"], "speed": 1.1, "cost": 2.2},
        {"id": "a3", "name": "Agent 3", "skills": ["testing", "design", "planning"], "speed": 0.9, "cost": 1.8},
        {"id": "a4", "name": "Agent 4", "skills": ["research", "backend", "database"], "speed": 1.2, "cost": 2.5},
        {"id": "a5", "name": "Agent 5", "skills": ["security", "testing", "design"], "speed": 1.0, "cost": 2.1},
        {"id": "a6", "name": "Agent 6", "skills": ["writing", "planning", "testing"], "speed": 1.1, "cost": 2.0},
    ]
    return [
        Agent(
            id=d["id"],
            name=d["name"],
            skills=list(d["skills"]),
            speed=d["speed"],
            cost_per_unit=d["cost"],
            available=True,
            current_task=None,
        )
        for d in roster_defs
    ]


def generate_random_mission(mission_index: int, rng: random.Random) -> List[Task]:
    """
    Generate a random DAG of 5-14 tasks with at most 3 deps per task,
    drawn from the 8-skill vocabulary with est_time 1-8.
    """
    num_tasks = rng.randint(5, 14)
    tasks: List[Task] = []
    for i in range(num_tasks):
        task_id = f"t{i+1}"
        # Pick up to 3 dependencies from earlier tasks
        possible_deps = [f"t{j+1}" for j in range(i)]
        k = rng.randint(0, min(3, i))
        deps = rng.sample(possible_deps, k) if k > 0 else []
        skill = rng.choice(SKILL_VOCABULARY)
        est_time = float(rng.randint(1, 8))
        est_cost = round(est_time * rng.uniform(1.5, 3.0), 2)
        priority = rng.choice(["low", "medium", "high"])

        tasks.append(
            Task(
                id=task_id,
                name=f"Task {task_id}",
                required_skill=skill,
                est_time=est_time,
                est_cost=est_cost,
                priority=priority,
                deps=deps,
                status="blocked",
            )
        )
    return tasks


def assert_scheduler_invariants(tasks: List[Task], agents: List[Agent], schedule: Schedule) -> None:
    """
    Assert scheduler invariants before execution:
    1. Single assignment: all tasks assigned exactly once.
    2. Dependency ordering: start_time >= max(dep.end_time).
    3. No agent overlap: no two tasks on the same agent overlap in time.
    """
    # 1. All tasks assigned exactly once
    assert len(schedule.assignments) == len(tasks), (
        f"Expected {len(tasks)} assignments, got {len(schedule.assignments)}"
    )
    assigned_ids = [a.task_id for a in schedule.assignments]
    assert len(assigned_ids) == len(set(assigned_ids)), "Duplicate task assignments found"
    assert set(assigned_ids) == {t.id for t in tasks}, "Not all tasks assigned"

    asgn_map = {a.task_id: a for a in schedule.assignments}
    task_map = {t.id: t for t in tasks}

    # 2. Dependency ordering
    for tid, asgn in asgn_map.items():
        task = task_map[tid]
        for dep_id in task.deps:
            assert dep_id in asgn_map, f"Dependency {dep_id} of task {tid} not scheduled"
            dep_end = asgn_map[dep_id].end_time
            assert asgn.start_time >= dep_end - 1e-6, (
                f"Task {tid} start {asgn.start_time} before dep {dep_id} end {dep_end}"
            )

    # 3. No agent overlap
    agent_tasks: Dict[str, list] = {}
    for a in schedule.assignments:
        agent_tasks.setdefault(a.agent_id, []).append(a)

    for aid, assignments in agent_tasks.items():
        sorted_asgns = sorted(assignments, key=lambda x: (x.start_time, x.end_time))
        for i in range(len(sorted_asgns) - 1):
            curr, nxt = sorted_asgns[i], sorted_asgns[i + 1]
            assert curr.end_time <= nxt.start_time + 1e-6, (
                f"Overlap on agent {aid}: {curr.task_id} [{curr.start_time}, {curr.end_time}] "
                f"overlaps {nxt.task_id} [{nxt.start_time}, {nxt.end_time}]"
            )


@pytest.mark.asyncio
async def test_fuzz_200_missions_scheduler_and_single_kill_recovery() -> None:
    """
    Generate 200 random missions (5-14 tasks, random DAG with <= 3 deps per task,
    8-skill vocabulary, est_time 1-8) and a 6-agent roster where every skill is on >= 2 agents.

    Assert scheduler invariants on each random mission before execution.
    Run each through Engine with SWARM_BASE_DELAY tiny (0.004), kill ONE random agent
    at a random time (0-0.04s), and assert:
    - Mission completes (status == "done")
    - No task completes twice
    - Every task starts after its dependencies are done
    - A dead agent never starts or finishes a task after its agent_failed event
    - No hang (5s timeout)
    """
    # Use Windows multimedia timer for precision if on Windows
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

    rng = random.Random(42)
    scheduler = GreedyScheduler()

    # Pre-generate 200 missions
    missions = [generate_random_mission(i, rng) for i in range(200)]

    try:
        for idx, tasks in enumerate(missions):
            base_roster = make_6_agent_roster()

            # 1. Assert scheduler invariants before execution
            schedule = scheduler.greedy_schedule(
                [copy.deepcopy(t) for t in tasks],
                [copy.deepcopy(a) for a in base_roster],
            )
            assert_scheduler_invariants(tasks, base_roster, schedule)

            # 2. Setup engine for execution
            task_dict = {t.id: copy.deepcopy(t) for t in tasks}
            agent_dict = {a.id: copy.deepcopy(a) for a in base_roster}
            state = MissionState(
                mission_id=f"fuzz-mission-{idx+1}",
                mission=f"Fuzz Mission {idx+1}",
                tasks=task_dict,
                agents=agent_dict,
            )
            clock = SimClock(base_delay=0.004)
            engine = Engine(state=state, clock=clock, tick_duration=0.002)

            # Start execution
            await engine.start()

            # Kill ONE random agent at random time (0-0.04s)
            kill_delay = rng.uniform(0.0, 0.04)
            await asyncio.sleep(kill_delay)

            victim_id = rng.choice(list(agent_dict.keys()))
            if engine.state.status == "running":
                await engine.handle_event({"type": "agent_failure", "agent_id": victim_id})

            # Wait for completion (5s timeout: no hang)
            await engine.wait_until_done(timeout=5.0)

            # Assertion 1: Mission completes
            assert engine.state.status == "done", (
                f"Mission {idx+1} failed to complete: {engine.state.status} ({engine.state.failed_reason})"
            )
            assert len(engine.state.done) == len(tasks), (
                f"Mission {idx+1}: Expected {len(tasks)} done, got {len(engine.state.done)}"
            )

            # Analyze event log
            event_log = engine.state.event_log
            done_counts: Dict[str, int] = {}
            dep_done_order: Dict[str, int] = {}
            started_events: List[Tuple[int, str, str]] = []  # (event_seq, task_id, agent_id)
            agent_failed_seq: int = sys.maxsize

            for ev in event_log:
                seq = ev.get("seq", 0)
                ev_type = ev.get("type")
                tid = ev.get("task_id")
                aid = ev.get("agent_id")

                if ev_type == "agent_failed" and aid == victim_id:
                    agent_failed_seq = seq

                elif ev_type == "task_started":
                    started_events.append((seq, tid, aid))

                elif ev_type == "task_done" and tid:
                    done_counts[tid] = done_counts.get(tid, 0) + 1
                    dep_done_order[tid] = seq

            # Assertion 2: No task completes twice
            for tid in tasks:
                assert done_counts.get(tid.id) == 1, (
                    f"Mission {idx+1}: Task {tid.id} completed {done_counts.get(tid.id)} times"
                )

            # Assertion 3: Every task starts after its dependencies are done
            for seq, tid, aid in started_events:
                task_obj = state.tasks[tid]
                for dep in task_obj.deps:
                    assert dep in dep_done_order, (
                        f"Mission {idx+1}: Task {tid} started before dep {dep} was completed"
                    )
                    assert dep_done_order[dep] < seq, (
                        f"Mission {idx+1}: Task {tid} started at seq {seq} before dep {dep} completed at seq {dep_done_order[dep]}"
                    )

            # Assertion 4: Dead agent never starts or finishes a task after its agent_failed event
            if agent_failed_seq < sys.maxsize:
                for ev in event_log:
                    seq = ev.get("seq", 0)
                    if seq > agent_failed_seq:
                        ev_type = ev.get("type")
                        aid = ev.get("agent_id")
                        assert not (ev_type in ("task_started", "task_done") and aid == victim_id), (
                            f"Mission {idx+1}: Dead agent {victim_id} performed {ev_type} at seq {seq} after agent_failed at seq {agent_failed_seq}"
                        )

    finally:
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_fuzz_two_kill_recovery() -> None:
    """
    Run 2-kill cases on random missions and assert only that:
    - Run ends in mission_done or mission_failed
    - No hang (5s timeout)
    - No duplicate completions
    - No dependency violations
    """
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

    rng = random.Random(1337)

    try:
        for idx in range(30):
            tasks = generate_random_mission(idx, rng)
            base_roster = make_6_agent_roster()

            task_dict = {t.id: copy.deepcopy(t) for t in tasks}
            agent_dict = {a.id: copy.deepcopy(a) for a in base_roster}

            state = MissionState(
                mission_id=f"fuzz-2kill-{idx+1}",
                mission=f"Fuzz 2-Kill {idx+1}",
                tasks=task_dict,
                agents=agent_dict,
            )
            clock = SimClock(base_delay=0.004)
            engine = Engine(state=state, clock=clock, tick_duration=0.002)

            await engine.start()

            # Kill 1st agent
            await asyncio.sleep(rng.uniform(0.001, 0.02))
            all_agents = list(agent_dict.keys())
            victim_1 = rng.choice(all_agents)
            if engine.state.status == "running":
                await engine.handle_event({"type": "agent_failure", "agent_id": victim_1})

            # Kill 2nd distinct agent
            await asyncio.sleep(rng.uniform(0.002, 0.02))
            remaining_agents = [aid for aid in all_agents if aid != victim_1]
            victim_2 = rng.choice(remaining_agents)
            if engine.state.status == "running":
                await engine.handle_event({"type": "agent_failure", "agent_id": victim_2})

            # Wait for completion (5s timeout: no hang)
            await engine.wait_until_done(timeout=5.0)

            # Assertion 1: Ends in mission_done or mission_failed
            assert engine.state.status in ("done", "failed"), (
                f"Run {idx+1} ended in unexpected status: {engine.state.status}"
            )

            # Assertion 2: No duplicate completions
            event_log = engine.state.event_log
            done_counts: Dict[str, int] = {}
            dep_done_order: Dict[str, int] = {}
            started_events: List[Tuple[int, str, str]] = []

            for ev in event_log:
                seq = ev.get("seq", 0)
                ev_type = ev.get("type")
                tid = ev.get("task_id")
                aid = ev.get("agent_id")

                if ev_type == "task_started":
                    started_events.append((seq, tid, aid))
                elif ev_type == "task_done" and tid:
                    done_counts[tid] = done_counts.get(tid, 0) + 1
                    dep_done_order[tid] = seq

            for tid, count in done_counts.items():
                assert count <= 1, f"Task {tid} completed {count} times in run {idx+1}"

            # Assertion 3: No dependency violations
            for seq, tid, aid in started_events:
                task_obj = state.tasks[tid]
                for dep in task_obj.deps:
                    assert dep in dep_done_order, (
                        f"Run {idx+1}: Task {tid} started before dep {dep} finished"
                    )
                    assert dep_done_order[dep] < seq, (
                        f"Run {idx+1}: Task {tid} started at seq {seq} before dep {dep} finished at seq {dep_done_order[dep]}"
                    )

    finally:
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
