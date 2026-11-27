"""
SWARMFORGE Re-Optimizer
=======================
Handles dynamic re-planning when runtime events occur:

  - "agent_failure" : Remove a failed agent and reschedule its tasks.
  - "budget_cut"    : Disable agents whose cost_per_unit exceeds the new
                      budget cap, then reschedule with remaining agents.
  - "task_added"    : Insert a new task and reschedule everything.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import Agent, Schedule, Task
from .scheduler import GreedyScheduler


class ReOptimizer:
    """Reacts to runtime events and produces an updated Schedule."""

    def __init__(self, scheduler: GreedyScheduler | None = None) -> None:
        self._scheduler = scheduler or GreedyScheduler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replan(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        current_tasks: List[Task],
        current_agents: List[Agent],
        current_schedule: Schedule,
        dag=None,
    ) -> Schedule:
        """
        React to a runtime event and return a fresh Schedule.

        Parameters
        ----------
        event_type       : One of "agent_failure", "budget_cut", "task_added".
        event_data       : Dict carrying event-specific payload (see below).
        current_tasks    : Full list of Task objects to reschedule.
        current_agents   : Full list of Agent objects currently registered.
        current_schedule : The Schedule that was active before the event.
        dag              : Optional DAG passed through to the scheduler.

        event_data shapes
        -----------------
        agent_failure -> {"agent_id": str}
        budget_cut    -> {"new_budget": float}
        task_added    -> {"task": Task}
        """

        if event_type == "agent_failure":
            return self._handle_agent_failure(
                event_data, current_tasks, current_agents, current_schedule, dag
            )

        elif event_type == "budget_cut":
            return self._handle_budget_cut(
                event_data, current_tasks, current_agents, current_schedule, dag
            )

        elif event_type == "task_added":
            return self._handle_task_added(
                event_data, current_tasks, current_agents, current_schedule, dag
            )

        else:
            raise ValueError(
                f"Unknown event_type: {event_type!r}. "
                "Expected one of: 'agent_failure', 'budget_cut', 'task_added'."
            )

    # ------------------------------------------------------------------
    # Private event handlers
    # ------------------------------------------------------------------

    def _handle_agent_failure(
        self,
        event_data: Dict[str, Any],
        tasks: List[Task],
        agents: List[Agent],
        schedule: Schedule,
        dag,
    ) -> Schedule:
        """
        Remove the failed agent from the pool and reschedule all tasks
        with the surviving agents.
        """
        failed_id: str = event_data["agent_id"]

        surviving_agents: List[Agent] = [
            a for a in agents if a.id != failed_id
        ]

        if not surviving_agents:
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        return self._scheduler.greedy_schedule(tasks, surviving_agents, dag)

    def _handle_budget_cut(
        self,
        event_data: Dict[str, Any],
        tasks: List[Task],
        agents: List[Agent],
        schedule: Schedule,
        dag,
    ) -> Schedule:
        """
        FEATURE: Budget Cut Handling
        ----------------------------
        Receives event_data = {"new_budget": float}.

        Any agent whose cost_per_unit exceeds new_budget has its
        `available` attribute set to False so the scheduler will
        skip them when assigning tasks.

        The updated agent list (with some agents now marked unavailable)
        is passed to the scheduler for a fresh run.
        """
        new_budget: float = float(event_data["new_budget"])

        for agent in agents:
            if agent.cost_per_unit > new_budget:
                agent.available = False

        # Only pass agents that are still available to the scheduler
        affordable_agents: List[Agent] = [
            a for a in agents if a.available
        ]

        if not affordable_agents:
            # No affordable agents remain — return an empty schedule
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        return self._scheduler.greedy_schedule(tasks, affordable_agents, dag)

    def _handle_task_added(
        self,
        event_data: Dict[str, Any],
        tasks: List[Task],
        agents: List[Agent],
        schedule: Schedule,
        dag,
    ) -> Schedule:
        """
        Append the new task to the task list and reschedule everything
        from scratch so dependency ordering is preserved.
        """
        new_task: Task = event_data["task"]
        updated_tasks: List[Task] = list(tasks) + [new_task]

        available_agents: List[Agent] = [a for a in agents if a.available]

        if not available_agents:
            return Schedule(assignments=[], makespan=0.0, total_cost=0.0)

        return self._scheduler.greedy_schedule(updated_tasks, available_agents, dag)