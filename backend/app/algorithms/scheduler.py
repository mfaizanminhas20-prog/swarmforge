"""
SWARMFORGE Scheduler
====================
Advanced Features:
  - Load Balancing: Penalises agents with many assigned tasks using a load counter.
  - Priority Pre-emption (simulated): "high" priority tasks are always sorted
    first so they are consumed before "medium"/"low" tasks at every time-step.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from .models import Agent, Schedule, ScheduledTask, Task


# Priority ranking: lower number = higher urgency
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


class GreedyScheduler:
    """Greedy list-scheduler with load-balancing and priority pre-emption."""

    def greedy_schedule(
        self,
        tasks: List[Task],
        agents: List[Agent],
        dag=None,
    ) -> Schedule:
        """
        Schedule all tasks respecting dependencies, balancing agent load,
        and always processing high-priority tasks before lower-priority ones.

        Returns a Schedule with assignments, makespan, and total_cost.
        """

        if not agents:
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        if not tasks:
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        # --- FEATURE: Load Balancing ---
        # Track how many tasks each agent has been assigned.
        agent_load: dict[str, int] = {agent.id: 0 for agent in agents}

        # agent_id -> earliest time the agent is free
        agent_free: dict[str, float] = {agent.id: 0.0 for agent in agents}

        # task_id -> Task for fast lookup
        task_map: dict[str, Task] = {t.id: t for t in tasks}

        # Set of task IDs that have been fully scheduled (treated as finished)
        finished: set[str] = set()

        # Set of task IDs still needing to be scheduled
        remaining: set[str] = set(task_map.keys())

        scheduled_tasks: List[ScheduledTask] = []
        total_cost: float = 0.0
        current_time: float = 0.0

        while remaining:
            # ------------------------------------------------------------------
            # 1. Collect tasks whose dependencies are all satisfied
            # ------------------------------------------------------------------
            available: List[Task] = [
                task_map[tid]
                for tid in remaining
                if all(dep in finished for dep in (task_map[tid].deps or []))
            ]

            if not available:
                # No task is ready yet — advance clock to the next agent
                # finishing event so dependencies can be unlocked.
                future_free_times = [
                    agent_free[agent.id]
                    for agent in agents
                    if agent_free[agent.id] > current_time
                ]
                if not future_free_times:
                    # Deadlock guard: break to avoid infinite loop
                    break
                current_time = min(future_free_times)

                # Mark any tasks that have finished by current_time
                for st in scheduled_tasks:
                    if st.end_time <= current_time:
                        finished.add(st.task_id)
                continue

            # ------------------------------------------------------------------
            # 2. FEATURE: Priority Pre-emption (simulated)
            #    Sort available tasks so "high" priority always comes first.
            #    Ties are broken by task id for deterministic output.
            # ------------------------------------------------------------------
            available.sort(
                key=lambda t: (
                    PRIORITY_RANK.get(
                        (t.priority or "medium").lower(), 1
                    ),
                    t.id,
                )
            )

            # ------------------------------------------------------------------
            # 3. Assign each available task to the best-scoring agent
            # ------------------------------------------------------------------
            assigned_this_round: set[str] = set()

            for task in available:
                # Only process tasks that are truly ready
                if not all(dep in finished for dep in (task.deps or [])):
                    continue

                best_agent: Optional[Agent] = None
                best_score: float = float("-inf")

                for agent in agents:
                    # Skip unavailable agents
                    if not agent.available:
                        continue

                    # Skip agents that lack the required skill
                    if task.required_skill and task.required_skill not in (agent.skills or []):
                        continue

                    # ----------------------------------------------------------
                    # FEATURE: Load Balancing scoring formula
                    # score = speed / (cost_per_unit + 0.1) - (load * 0.5)
                    # ----------------------------------------------------------
                    score: float = (
                        agent.speed / (agent.cost_per_unit + 0.1)
                    ) - (agent_load[agent.id] * 0.5)

                    if score > best_score:
                        best_score = score
                        best_agent = agent

                if best_agent is None:
                    # No eligible agent found for this task; skip for now
                    continue

                # Compute timing
                start_time: float = max(
                    agent_free[best_agent.id], current_time
                )
                duration: float = task.est_time / best_agent.speed
                end_time: float = start_time + duration
                task_cost: float = duration * best_agent.cost_per_unit

                # Record the scheduled task
                st = ScheduledTask(
                    task_id=task.id,
                    agent_id=best_agent.id,
                    start_time=start_time,
                    end_time=end_time,
                )
                scheduled_tasks.append(st)
                total_cost += task_cost

                # Update bookkeeping
                agent_free[best_agent.id] = end_time
                agent_load[best_agent.id] += 1          # Load Balancing update
                assigned_this_round.add(task.id)
                remaining.discard(task.id)
                finished.add(task.id)

            # If nothing could be assigned this round, advance the clock
            if not assigned_this_round:
                future_free_times = [
                    agent_free[agent.id]
                    for agent in agents
                    if agent_free[agent.id] > current_time
                ]
                if not future_free_times:
                    break  # Deadlock guard
                current_time = min(future_free_times)
                for st in scheduled_tasks:
                    if st.end_time <= current_time:
                        finished.add(st.task_id)

        # Makespan = time the last task finishes
        makespan: float = (
            max(st.end_time for st in scheduled_tasks)
            if scheduled_tasks
            else 0.0
        )

        return Schedule(
            assignments=scheduled_tasks,
            makespan=makespan,
            total_cost=total_cost,
        )
    # Compatibility alias for backend and tests
Scheduler = GreedyScheduler