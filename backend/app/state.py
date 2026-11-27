"""
MissionState and SimClock for the SWARMFORGE execution engine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import os
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Set

from app.algorithms.models import Agent, Schedule, Task

logger = logging.getLogger(__name__)


@dataclass
class MissionState:
    """Represents the global execution state of a mission."""

    mission_id: str
    mission: str
    tasks: Dict[str, Task] = field(default_factory=dict)
    agents: Dict[str, Agent] = field(default_factory=dict)
    done: Set[str] = field(default_factory=set)
    running: Dict[str, str] = field(default_factory=dict)  # task_id -> agent_id
    dead: Set[str] = field(default_factory=set)  # dead agent ids
    current_schedule: Optional[Schedule] = None
    status: Literal["idle", "running", "done", "failed"] = "idle"
    failed_reason: Optional[str] = None
    event_log: List[Dict[str, Any]] = field(default_factory=list)
    actual_cost: float = 0.0
    wasted_cost: float = 0.0
    failures_recovered: int = 0
    initial_tasks: List[Task] = field(default_factory=list)
    initial_agents: List[Agent] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize collection inputs if initialized with alternate types."""
        if isinstance(self.tasks, list):
            self.tasks = {t.id: t for t in self.tasks}
        if isinstance(self.agents, list):
            self.agents = {a.id: a for a in self.agents}
        if isinstance(self.done, (list, tuple)):
            self.done = set(self.done)
        if isinstance(self.dead, (list, tuple)):
            self.dead = set(self.dead)
        if not self.initial_tasks and self.tasks:
            self.initial_tasks = [
                Task.from_dict(t.to_dict()) if hasattr(t, "to_dict") else t
                for t in self.tasks.values()
            ]
        if not self.initial_agents and self.agents:
            self.initial_agents = [
                Agent.from_dict(a.to_dict()) if hasattr(a, "to_dict") else a
                for a in self.agents.values()
            ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to a JSON-serializable dictionary."""
        return {
            "mission_id": self.mission_id,
            "mission": self.mission,
            "tasks": {
                k: v.to_dict() if hasattr(v, "to_dict") else v
                for k, v in self.tasks.items()
            },
            "agents": {
                k: v.to_dict() if hasattr(v, "to_dict") else v
                for k, v in self.agents.items()
            },
            "done": sorted(list(self.done)),
            "running": dict(self.running),
            "dead": sorted(list(self.dead)),
            "current_schedule": (
                self.current_schedule.to_dict()
                if self.current_schedule is not None and hasattr(self.current_schedule, "to_dict")
                else self.current_schedule
            ),
            "status": self.status,
            "failed_reason": self.failed_reason,
            "event_log": list(self.event_log),
            "actual_cost": self.actual_cost,
            "wasted_cost": self.wasted_cost,
            "failures_recovered": self.failures_recovered,
        }


class SimClock:
    """
    Simulation Clock for time-scaled execution.

    now() returns simulated time units, advancing by:
        wall_delta * multiplier / base_delay

    base_delay (wall seconds per simulated unit) is obtained from the
    SWARM_BASE_DELAY environment variable, defaulting to 0.5.

    When multiplier (or base_delay) changes mid-run, anchor values are preserved
    to guarantee smooth continuity without time jumps or loss of elapsed simulated time.
    """

    def __init__(
        self,
        multiplier: float = 1.0,
        base_delay: Optional[float] = None,
        time_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if base_delay is None:
            env_val = os.getenv("SWARM_BASE_DELAY")
            self._base_delay: float = float(env_val) if env_val is not None else 0.5
        else:
            self._base_delay = float(base_delay)

        if self._base_delay <= 0:
            raise ValueError(f"base_delay must be positive, got {self._base_delay}")

        self._time_fn: Callable[[], float] = time_fn if time_fn is not None else time.monotonic
        self._multiplier: float = float(multiplier)
        self._wall_anchor: float = self._time_fn()
        self._sim_anchor: float = 0.0
        logger.debug(
            "SimClock initialized: base_delay=%.3f, multiplier=%.3f",
            self._base_delay,
            self._multiplier,
        )

    @property
    def base_delay(self) -> float:
        """Wall seconds per simulated unit."""
        return self._base_delay

    @base_delay.setter
    def base_delay(self, value: float) -> None:
        if value <= 0:
            raise ValueError(f"base_delay must be positive, got {value}")
        current_sim = self.now()
        self._sim_anchor = current_sim
        self._wall_anchor = self._time_fn()
        self._base_delay = float(value)
        logger.debug("SimClock base_delay changed to %.3f at sim=%.3f", self._base_delay, current_sim)

    @property
    def multiplier(self) -> float:
        """Current speed multiplier."""
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value: float) -> None:
        self.set_multiplier(value)

    def set_multiplier(self, new_multiplier: float) -> None:
        """Change speed multiplier mid-run while maintaining continuous simulated time."""
        current_sim = self.now()
        self._sim_anchor = current_sim
        self._wall_anchor = self._time_fn()
        self._multiplier = float(new_multiplier)
        logger.debug("SimClock multiplier set to %.3f at sim=%.3f", self._multiplier, current_sim)

    def now(self) -> float:
        """Return the current simulated time units."""
        current_wall = self._time_fn()
        wall_delta = current_wall - self._wall_anchor
        return self._sim_anchor + (wall_delta * self._multiplier / self._base_delay)

    def reset(self, sim_time: float = 0.0) -> None:
        """Reset the simulation clock to the given simulated time."""
        self._wall_anchor = self._time_fn()
        self._sim_anchor = float(sim_time)
        logger.debug("SimClock reset to sim=%.3f", self._sim_anchor)
