"""
Tests for Algorithm Arena: GreedyScheduler vs FCFSScheduler baseline.
Validates:
1. Prompt 1 invariants on both Greedy and FCFS schedules (demo_wide.json and agents_default.json):
   - Single assignment: every task is assigned exactly once.
   - Dependency ordering: task.start_time >= max(dep.end_time).
   - Agent non-overlap: no two tasks on the same agent overlap in time.
2. Assert greedy makespan <= fcfs makespan AND greedy total_cost <= fcfs total_cost on demo_wide.json.
3. If greedy does not win, print both results in a table and stop for discussion with algorithm owner.
4. GET /compare and GET /report API endpoint verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import List, Tuple
import pytest
from fastapi.testclient import TestClient

import app.main as api_main
from app.algorithms.fcfs import FCFSScheduler
from app.algorithms.models import Agent, Schedule, Task
from app.algorithms.scheduler import GreedyScheduler


@pytest.fixture(autouse=True)
def clean_engine_state():
    """Reset engine state before and after each test."""
    if api_main.current_engine is not None:
        try:
            for worker in list(api_main.current_engine._worker_tasks.values()):
                if not worker.done():
                    worker.cancel()
        except Exception:
            pass
    api_main.current_engine = None
    api_main.task_start_times.clear()
    api_main.task_end_times.clear()
    api_main.manager.active_connections.clear()
    yield
    if api_main.current_engine is not None:
        try:
            for worker in list(api_main.current_engine._worker_tasks.values()):
                if not worker.done():
                    worker.cancel()
        except Exception:
            pass
    api_main.current_engine = None
    api_main.task_start_times.clear()
    api_main.task_end_times.clear()
    api_main.manager.active_connections.clear()


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient with an active BlockingPortal lifespan."""
    with TestClient(api_main.app) as c:
        yield c


def load_demo_wide_fixtures() -> Tuple[List[Task], List[Agent]]:
    """Load tasks and agents for demo_wide benchmark."""
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    demo_path = fixtures_dir / "demo_wide.json"
    agents_path = fixtures_dir / "agents_default.json"

    with open(demo_path, "r", encoding="utf-8") as f:
        demo_data = json.load(f)
    with open(agents_path, "r", encoding="utf-8") as f:
        agents_data = json.load(f)

    tasks = [Task.from_dict(t) for t in demo_data["tasks"]]
    agents_list = agents_data if isinstance(agents_data, list) else agents_data.get("agents", [])
    agents = [Agent.from_dict(a) for a in agents_list]
    return tasks, agents


def assert_prompt1_invariants(tasks: List[Task], schedule: Schedule, algorithm_name: str) -> None:
    """Validate the core Prompt 1 invariants on a schedule."""
    # Invariant 1: Single assignment - every task assigned exactly once
    assert len(schedule.assignments) == len(tasks), (
        f"[{algorithm_name}] Expected {len(tasks)} assignments, got {len(schedule.assignments)}"
    )
    assigned_ids = [a.task_id for a in schedule.assignments]
    assert len(assigned_ids) == len(set(assigned_ids)), (
        f"[{algorithm_name}] Duplicate task assignments found in schedule"
    )
    assert set(assigned_ids) == {t.id for t in tasks}, (
        f"[{algorithm_name}] Assigned task IDs do not match input task set"
    )

    assignment_map = {a.task_id: a for a in schedule.assignments}
    task_map = {t.id: t for t in tasks}

    # Invariant 2: Dependency ordering - start_time >= max(dep.end_time)
    for task_id, assignment in assignment_map.items():
        task = task_map[task_id]
        for dep_id in (task.deps or []):
            assert dep_id in assignment_map, (
                f"[{algorithm_name}] Dependency {dep_id} was not scheduled for {task_id}"
            )
            dep_end = assignment_map[dep_id].end_time
            assert assignment.start_time >= dep_end - 1e-6, (
                f"[{algorithm_name}] Dependency violation: Task {task_id} starts at "
                f"{assignment.start_time:.3f} before dependency {dep_id} ends at {dep_end:.3f}"
            )

    # Invariant 3: Agent non-overlap - no two assignments on the same agent overlap
    agent_tasks: dict[str, list] = {}
    for a in schedule.assignments:
        agent_tasks.setdefault(a.agent_id, []).append(a)

    for agent_id, assignments in agent_tasks.items():
        sorted_assignments = sorted(assignments, key=lambda x: (x.start_time, x.end_time))
        for i in range(len(sorted_assignments) - 1):
            curr = sorted_assignments[i]
            nxt = sorted_assignments[i + 1]
            assert curr.end_time <= nxt.start_time + 1e-6, (
                f"[{algorithm_name}] Overlap on agent {agent_id}: task {curr.task_id} "
                f"[{curr.start_time:.3f}, {curr.end_time:.3f}] overlaps with "
                f"task {nxt.task_id} [{nxt.start_time:.3f}, {nxt.end_time:.3f}]"
            )


def test_arena_invariants_and_benchmark_on_demo_wide() -> None:
    """
    Validate invariants for both Greedy and FCFS schedulers on demo_wide.json.
    Assert that Greedy achieves <= makespan AND <= total_cost compared to FCFS.
    """
    tasks, agents = load_demo_wide_fixtures()

    # Create fresh copies for both schedulers
    greedy_tasks = [Task.from_dict(t.to_dict()) for t in tasks]
    greedy_agents = [Agent.from_dict(a.to_dict()) for a in agents]
    greedy_scheduler = GreedyScheduler()
    greedy_sched = greedy_scheduler.greedy_schedule(greedy_tasks, greedy_agents)

    fcfs_tasks = [Task.from_dict(t.to_dict()) for t in tasks]
    fcfs_agents = [Agent.from_dict(a.to_dict()) for a in agents]
    fcfs_scheduler = FCFSScheduler()
    fcfs_sched = fcfs_scheduler.greedy_schedule(fcfs_tasks, fcfs_agents)

    # 1. Validate Prompt 1 invariants on BOTH schedules
    assert_prompt1_invariants(tasks, greedy_sched, "GreedyScheduler")
    assert_prompt1_invariants(tasks, fcfs_sched, "FCFSScheduler")

    # 2. Check if greedy wins
    time_improvement = (
        (fcfs_sched.makespan - greedy_sched.makespan) / fcfs_sched.makespan * 100
        if fcfs_sched.makespan > 0
        else 0.0
    )
    cost_improvement = (
        (fcfs_sched.total_cost - greedy_sched.total_cost) / fcfs_sched.total_cost * 100
        if fcfs_sched.total_cost > 0
        else 0.0
    )

    greedy_makespan_win = greedy_sched.makespan <= fcfs_sched.makespan
    greedy_cost_win = greedy_sched.total_cost <= fcfs_sched.total_cost
    greedy_wins = greedy_makespan_win and greedy_cost_win

    if not greedy_wins:
        # Format table for discussion with algorithm owners
        table = (
            "\n"
            "+===============================================================+\n"
            "|                     SWARMFORGE ARENA RESULTS                  |\n"
            "+================+====================+=========================+\n"
            "| Algorithm      | Makespan (sim sec) | Total Cost ($)          |\n"
            "+----------------+--------------------+-------------------------+\n"
            f"| Greedy         | {greedy_sched.makespan:18.2f} | {greedy_sched.total_cost:23.2f} |\n"
            f"| FCFS           | {fcfs_sched.makespan:18.2f} | {fcfs_sched.total_cost:23.2f} |\n"
            "+----------------+--------------------+-------------------------+\n"
            f"| Improvement    | {time_improvement:17.2f}% | {cost_improvement:22.2f}% |\n"
            "+================+====================+=========================+\n"
            "\nIf the Arena test fails: message Faizan and Huzaifa with the numbers.\n"
            "Possible fixes belong to Faizan's scheduler (e.g., critical-path priority,\n"
            "earliest-finish agent selection) or to the demo mission, not to the FCFS baseline.\n"
        )
        print(table)

    assert greedy_makespan_win, (
        f"Greedy makespan ({greedy_sched.makespan:.2f}) > FCFS makespan ({fcfs_sched.makespan:.2f})"
    )
    assert greedy_cost_win, (
        f"Greedy total_cost ({greedy_sched.total_cost:.2f}) > FCFS total_cost ({fcfs_sched.total_cost:.2f})"
    )


def test_compare_endpoint_demo_wide(client: TestClient) -> None:
    """Test GET /compare returns both greedy, fcfs, and improvement metrics."""
    resp = client.get("/compare?fixture=demo_wide")
    assert resp.status_code == 200
    data = resp.json()

    assert "greedy" in data
    assert "fcfs" in data
    assert "improvement" in data

    assert data["greedy"]["makespan"] > 0
    assert data["greedy"]["total_cost"] > 0
    assert len(data["greedy"]["assignments"]) == 12

    assert data["fcfs"]["makespan"] > 0
    assert data["fcfs"]["total_cost"] > 0
    assert len(data["fcfs"]["assignments"]) == 12

    # Verify greedy wins on demo_wide
    assert data["greedy"]["makespan"] <= data["fcfs"]["makespan"]
    assert data["greedy"]["total_cost"] <= data["fcfs"]["total_cost"]
    assert data["improvement"]["time_pct"] >= 0.0
    assert data["improvement"]["cost_pct"] >= 0.0


def test_compare_endpoint_with_active_mission_and_agent_kill(client: TestClient) -> None:
    """
    Test GET /compare with an active mission uses INITIAL tasks and full initial roster
    unaffected by mid-run agent kills.
    """
    # Create mission
    m_resp = client.post("/mission", json={"fixture": "demo_wide"})
    assert m_resp.status_code == 200

    # Start mission
    s_resp = client.post("/mission/start")
    assert s_resp.status_code == 200

    # Simulate agent failure of a1
    ev_resp = client.post("/event", json={"type": "agent_failure", "agent_id": "a1"})
    assert ev_resp.status_code == 200

    # Call /compare; must evaluate initial roster (all 5 agents available)
    c_resp = client.get("/compare")
    assert c_resp.status_code == 200
    c_data = c_resp.json()

    assert len(c_data["greedy"]["assignments"]) == 12
    assert len(c_data["fcfs"]["assignments"]) == 12
    # Verify a1 is still in greedy/fcfs assignments because comparison uses initial roster
    greedy_agents = {a["agent_id"] for a in c_data["greedy"]["assignments"]}
    fcfs_agents = {a["agent_id"] for a in c_data["fcfs"]["assignments"]}
    assert "a1" in greedy_agents or "a1" in fcfs_agents


def test_report_endpoint_after_mission_done(client: TestClient) -> None:
    """
    Test GET /report after mission completion returns all required keys:
    {mission, status, total_time, total_cost, wasted_cost, tasks_completed,
     tasks_total, failures_recovered, failed_reason, event_log}.
    """
    # Fast base delay for test speed
    import os
    os.environ["SWARM_BASE_DELAY"] = "0.01"

    client.post("/mission", json={"fixture": "rest_api"})
    client.post("/mission/start")

    # Fast forward: set 4.0 speed
    client.post("/speed", json={"multiplier": 4.0})

    # Wait for completion
    for _ in range(150):
        s = client.get("/state").json()
        if s["status"] in ("done", "failed"):
            break
        time.sleep(0.02)

    resp = client.get("/report")
    assert resp.status_code == 200
    report = resp.json()

    assert report["mission"] == "Build and validate a secure REST API"
    assert report["status"] == "done"
    assert report["total_time"] > 0
    assert report["total_cost"] > 0
    assert report["wasted_cost"] == 0.0
    assert report["tasks_completed"] == 8
    assert report["tasks_total"] == 8
    assert report["failures_recovered"] == 0
    assert report["failed_reason"] is None
    assert isinstance(report["event_log"], list)
    assert len(report["event_log"]) > 0


def test_report_endpoint_after_mission_failed(client: TestClient) -> None:
    """
    Test GET /report after mission failure returns failed status, reason, and event log.
    """
    import os
    os.environ["SWARM_BASE_DELAY"] = "0.01"

    client.post("/mission", json={"fixture": "rest_api"})
    client.post("/mission/start")

    # Kill a3, the only agent with "testing" skill in rest_api.json
    ev_resp = client.post("/event", json={"type": "agent_failure", "agent_id": "a3"})
    assert ev_resp.status_code == 200

    resp = client.get("/report")
    assert resp.status_code == 200
    report = resp.json()

    assert report["status"] == "failed"
    assert report["failed_reason"] is not None
    assert "Unassignable tasks" in report["failed_reason"]
    assert report["failures_recovered"] == 0
    assert isinstance(report["event_log"], list)
