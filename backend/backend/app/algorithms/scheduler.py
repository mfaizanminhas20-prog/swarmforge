"""
scheduler.py  —  Greedy and FCFS schedulers for SWARMFORGE.
"""
from __future__ import annotations
from typing import List, Dict
from collections import defaultdict

from .models import Task, Agent, ScheduledTask, Schedule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topological_sort(tasks: List[Task]) -> List[Task]:
    """Return tasks in topological order (Kahn's algorithm)."""
    task_map: Dict[str, Task] = {t.id: t for t in tasks}
    in_degree: Dict[str, int] = {t.id: 0 for t in tasks}
    children:  Dict[str, List[str]] = {t.id: [] for t in tasks}

    for task in tasks:
        for dep in task.dependencies:
            if dep in task_map:
                in_degree[task.id] += 1
                children[dep].append(task.id)

    queue = sorted(
        [tid for tid, deg in in_degree.items() if deg == 0],
        key=lambda tid: -task_map[tid].priority,
    )
    ordered: List[Task] = []

    while queue:
        tid = queue.pop(0)
        ordered.append(task_map[tid])
        for child in sorted(children[tid], key=lambda c: -task_map[c].priority):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    return ordered


def _agent_score(agent: Agent) -> float:
    """Higher is better:  speed / cost_per_unit."""
    cost = agent.cost_per_unit if agent.cost_per_unit > 0 else 1e-9
    return agent.speed / cost


def _build_schedule(assignments: List[ScheduledTask], agents: List[Agent]) -> Schedule:
    """Derive makespan and total_cost from a list of ScheduledTask objects."""
    if not assignments:
        return Schedule()

    agent_map    = {a.id: a for a in agents}
    makespan     = max(a.end_time for a in assignments)
    total_cost   = sum(
        (a.end_time - a.start_time) * agent_map[a.agent_id].cost_per_unit
        for a in assignments
        if a.agent_id in agent_map
    )
    return Schedule(assignments=assignments, makespan=makespan, total_cost=total_cost)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """
    Two scheduling strategies that both return a :class:`Schedule` object.
    """

    # ------------------------------------------------------------------
    # Greedy
    # ------------------------------------------------------------------
    def greedy_schedule(
        self,
        tasks:  List[Task],
        agents: List[Agent],
    ) -> Schedule:
        """
        Process tasks in priority-aware topological order.
        For each task, pick the available agent with the highest
        ``speed / cost_per_unit`` score, subject to the agent being
        free and all dependencies being satisfied.
        """
        available = [a for a in agents if a.available]
        if not available:
            return Schedule()

        ordered        = _topological_sort([t for t in tasks if not t.completed])
        agent_free_at: Dict[str, float] = {a.id: 0.0 for a in available}
        finish_time:   Dict[str, float] = {}
        assignments:   List[ScheduledTask] = []

        for task in ordered:
            dep_ready = max(
                (finish_time[d] for d in task.dependencies if d in finish_time),
                default=0.0,
            )

            # Choose best agent (earliest ready, highest score as tie-break)
            best_agent  = None
            best_start  = float("inf")
            best_score  = -1.0

            for agent in available:
                ready = max(agent_free_at[agent.id], dep_ready)
                score = _agent_score(agent)
                if ready < best_start or (ready == best_start and score > best_score):
                    best_agent = agent
                    best_start = ready
                    best_score = score

            if best_agent is None:
                continue

            end_time = best_start + task.duration
            agent_free_at[best_agent.id] = end_time
            finish_time[task.id]         = end_time

            assignments.append(ScheduledTask(
                task_id    = task.id,
                agent_id   = best_agent.id,
                start_time = best_start,
                end_time   = end_time,
            ))

        return _build_schedule(assignments, agents)

    # ------------------------------------------------------------------
    # FCFS baseline
    # ------------------------------------------------------------------
    def fcfs_schedule(
        self,
        tasks:  List[Task],
        agents: List[Agent],
    ) -> Schedule:
        """
        First-Come First-Served: assign each task (in list order) to
        whichever agent becomes free soonest.  No priority, no scoring.
        """
        available = [a for a in agents if a.available]
        if not available:
            return Schedule()

        agent_free_at: Dict[str, float] = {a.id: 0.0 for a in available}
        finish_time:   Dict[str, float] = {}
        assignments:   List[ScheduledTask] = []

        for task in tasks:
            if task.completed:
                continue

            dep_ready = max(
                (finish_time[d] for d in task.dependencies if d in finish_time),
                default=0.0,
            )

            best_agent = min(available, key=lambda a: agent_free_at[a.id])
            start_time = max(agent_free_at[best_agent.id], dep_ready)
            end_time   = start_time + task.duration

            agent_free_at[best_agent.id] = end_time
            finish_time[task.id]         = end_time

            assignments.append(ScheduledTask(
                task_id    = task.id,
                agent_id   = best_agent.id,
                start_time = start_time,
                end_time   = end_time,
            ))

        return _build_schedule(assignments, agents)
