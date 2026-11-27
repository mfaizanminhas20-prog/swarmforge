"""
SWARMFORGE FCFS Scheduler
=========================
First-Come-First-Serve (FCFS) baseline scheduler.

Behaviour:
  - Repeatedly take the first task in INPUT order whose dependencies are all scheduled.
  - Assign it to the first available agent in list order that has the required skill.
  - No cost logic and no load balancing.
  - Timing rules match GreedyScheduler: start = max(agent_free, max end of deps).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .models import Agent, Schedule, ScheduledTask, Task

logger = logging.getLogger(__name__)


class FCFSScheduler:
    """First-Come-First-Serve baseline scheduler."""

    def greedy_schedule(
        self,
        tasks: List[Task],
        agents: List[Agent],
        dag=None,
    ) -> Schedule:
        """
        Schedule tasks using a pure First-Come-First-Serve policy.

        Takes the first task in input order whose dependencies are satisfied,
        and assigns it to the first eligible available agent in list order.
        """
        if not agents or not tasks:
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        # agent_id -> earliest time the agent is free
        agent_free: dict[str, float] = {agent.id: 0.0 for agent in agents}

        # task_id -> task end time
        end_of: dict[str, float] = {}

        # Set of task IDs that have been scheduled
        finished: set[str] = set()

        scheduled_tasks: List[ScheduledTask] = []
        total_cost: float = 0.0

        # Remaining tasks in original input order
        remaining: List[Task] = list(tasks)

        while remaining:
            assigned = False
            for i, task in enumerate(remaining):
                # Check if all dependencies are scheduled
                if all(dep in finished for dep in (task.deps or [])):
                    # Assign to first available agent in list order with required skill
                    eligible_agent: Optional[Agent] = None
                    for agent in agents:
                        if not agent.available:
                            continue
                        if task.required_skill and task.required_skill not in (agent.skills or []):
                            continue
                        eligible_agent = agent
                        break

                    if eligible_agent is None:
                        # No agent currently available/eligible for this task; inspect other candidates
                        continue

                    # Remove task from remaining queue
                    remaining.pop(i)

                    # Timing rule: start = max(agent_free, max end of deps)
                    dep_ready = max(
                        (end_of[d] for d in (task.deps or []) if d in end_of),
                        default=0.0,
                    )
                    start_time: float = max(agent_free[eligible_agent.id], dep_ready)
                    duration: float = task.est_time / eligible_agent.speed
                    end_time: float = start_time + duration
                    task_cost: float = duration * eligible_agent.cost_per_unit

                    st = ScheduledTask(
                        task_id=task.id,
                        agent_id=eligible_agent.id,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    scheduled_tasks.append(st)
                    total_cost += task_cost

                    # Update bookkeeping
                    agent_free[eligible_agent.id] = end_time
                    finished.add(task.id)
                    end_of[task.id] = end_time
                    assigned = True
                    break

            if not assigned:
                # Deadlock guard: no remaining task can be scheduled
                logger.warning(
                    "FCFS scheduling stalled with %d unscheduled tasks",
                    len(remaining),
                )
                break

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

    # Alias for explicit callers
    fcfs_schedule = greedy_schedule
