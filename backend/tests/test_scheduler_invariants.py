"""
Tests for scheduler invariants on realistic workloads (rest_api.json).
Invariants verified:
1. Dependency ordering: for every task, start_time >= max(end_time of its dependencies)
2. Agent non-overlap: no two assignments on the same agent overlap in time
3. Single assignment: every task is assigned exactly once
"""

import json
from pathlib import Path
import pytest

from app.algorithms.models import Agent, Schedule, Task
from app.algorithms.scheduler import GreedyScheduler


def load_rest_api_fixture() -> tuple[list[Task], list[Agent]]:
    # Look in backend/fixtures/rest_api.json or relative fixtures path
    current_dir = Path(__file__).resolve().parent
    fixture_path = current_dir.parent / "fixtures" / "rest_api.json"
    if not fixture_path.exists():
        fixture_path = Path("backend/fixtures/rest_api.json")
    if not fixture_path.exists():
        fixture_path = Path("fixtures/rest_api.json")

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = [Task.from_dict(t) for t in data["tasks"]]
    agents = [Agent.from_dict(a) for a in data["agents"]]
    return tasks, agents


def test_scheduler_invariants_rest_api() -> None:
    tasks, agents = load_rest_api_fixture()
    scheduler = GreedyScheduler()
    schedule: Schedule = scheduler.greedy_schedule(tasks, agents)

    # 1. Every task is assigned exactly once
    assert len(schedule.assignments) == len(tasks), (
        f"Expected {len(tasks)} assignments, got {len(schedule.assignments)}"
    )
    assigned_ids = [a.task_id for a in schedule.assignments]
    assert len(assigned_ids) == len(set(assigned_ids)), "Duplicate task assignments found"
    assert set(assigned_ids) == {t.id for t in tasks}, "Not all tasks were assigned"

    # Map of task_id to its assignment
    assignment_map = {a.task_id: a for a in schedule.assignments}
    task_map = {t.id: t for t in tasks}

    # 2. Dependency ordering: for every task, start >= max(end of its deps)
    for task_id, assignment in assignment_map.items():
        task = task_map[task_id]
        if task.deps:
            for dep_id in task.deps:
                assert dep_id in assignment_map, f"Dependency {dep_id} not scheduled for {task_id}"
                dep_end = assignment_map[dep_id].end_time
                assert assignment.start_time >= dep_end - 1e-6, (
                    f"Dependency violation: Task {task_id} starts at {assignment.start_time:.2f} "
                    f"before dependency {dep_id} ends at {dep_end:.2f}"
                )

    # 3. No two assignments on the same agent overlap in time
    agent_tasks: dict[str, list] = {}
    for a in schedule.assignments:
        agent_tasks.setdefault(a.agent_id, []).append(a)

    for agent_id, assignments in agent_tasks.items():
        # Sort by start_time
        sorted_assignments = sorted(assignments, key=lambda x: (x.start_time, x.end_time))
        for i in range(len(sorted_assignments) - 1):
            curr = sorted_assignments[i]
            nxt = sorted_assignments[i + 1]
            assert curr.end_time <= nxt.start_time + 1e-6, (
                f"Overlap on agent {agent_id}: task {curr.task_id} [{curr.start_time:.2f}, {curr.end_time:.2f}] "
                f"overlaps with task {nxt.task_id} [{nxt.start_time:.2f}, {nxt.end_time:.2f}]"
            )

    # 4. Expected metrics on rest_api.json
    # Expected result: 0 dependency violations, 0 overlaps, makespan ≈ 33.11, cost ≈ 93.58
    assert schedule.makespan == pytest.approx(33.11, abs=0.05)
    assert schedule.total_cost == pytest.approx(93.58, abs=0.05)
