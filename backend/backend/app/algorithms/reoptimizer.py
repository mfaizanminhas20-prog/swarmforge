"""
reoptimizer.py  —  Dynamic re-planner for SWARMFORGE.
"""
from __future__ import annotations
import copy
from typing import List, Dict, Any

from .models    import Task, Agent, Schedule
from .scheduler import Scheduler

EVENT_AGENT_FAILED = "agent_failed"
EVENT_TASK_ADDED   = "task_added"


class Reoptimizer:
    """
    Reacts to runtime disruptions and returns a fresh :class:`Schedule`.

    Supported events
    ----------------
    ``agent_failed``  — ``event_data={"agent_id": str}``
        Marks the named agent unavailable.

    ``task_added``    — ``event_data={"task": dict}``
        Inserts a new task into the queue.
    """

    def __init__(self):
        self._scheduler = Scheduler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def replan(
        self,
        tasks:      List[Task],
        agents:     List[Agent],
        event_type: str,
        event_data: Dict[str, Any],
    ) -> Schedule:
        """
        Apply *event_type*, then re-run the greedy scheduler on the
        remaining (incomplete) tasks and still-available agents.
        """
        tasks  = copy.deepcopy(tasks)
        agents = copy.deepcopy(agents)

        self._apply_event(tasks, agents, event_type, event_data)

        schedulable_tasks  = [t for t in tasks  if not t.completed]
        schedulable_agents = [a for a in agents if a.available]

        return self._scheduler.greedy_schedule(schedulable_tasks, schedulable_agents)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _apply_event(
        self,
        tasks:      List[Task],
        agents:     List[Agent],
        event_type: str,
        event_data: Dict[str, Any],
    ) -> None:
        if event_type == EVENT_AGENT_FAILED:
            self._handle_agent_failed(agents, event_data)
        elif event_type == EVENT_TASK_ADDED:
            self._handle_task_added(tasks, event_data)
        # Unknown events are silently ignored — schedule continues unchanged.

    @staticmethod
    def _handle_agent_failed(agents: List[Agent], event_data: Dict[str, Any]) -> None:
        failed_id = event_data.get("agent_id")
        for agent in agents:
            if agent.id == failed_id:
                agent.available = False

    @staticmethod
    def _handle_task_added(tasks: List[Task], event_data: Dict[str, Any]) -> None:
        raw = event_data.get("task")
        if not raw or not isinstance(raw, dict) or "id" not in raw:
            return
        existing_ids = {t.id for t in tasks}
        if raw["id"] not in existing_ids:
            tasks.append(Task.from_dict(raw))
