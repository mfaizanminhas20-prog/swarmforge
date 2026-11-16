"""
models.py  —  Core dataclasses for SWARMFORGE.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Task:
    id:           str
    duration:     float
    priority:     int                    = 1
    dependencies: List[str]             = field(default_factory=list)
    completed:    bool                  = False
    assigned_agent: Optional[str]       = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id             = data["id"],
            duration       = float(data.get("duration", 1)),
            priority       = int(data.get("priority", 1)),
            dependencies   = list(data.get("dependencies", [])),
            completed      = bool(data.get("completed", False)),
            assigned_agent = data.get("assigned_agent"),
        )


@dataclass
class Agent:
    id:           str
    speed:        float = 1.0
    cost_per_unit: float = 1.0
    available:    bool  = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Agent":
        return cls(
            id            = data["id"],
            speed         = float(data.get("speed", 1.0)),
            cost_per_unit = float(data.get("cost_per_unit", 1.0)),
            available     = bool(data.get("available", True)),
        )


@dataclass
class ScheduledTask:
    task_id:    str
    agent_id:   str
    start_time: float
    end_time:   float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        return cls(
            task_id    = data["task_id"],
            agent_id   = data["agent_id"],
            start_time = float(data["start_time"]),
            end_time   = float(data["end_time"]),
        )


@dataclass
class Schedule:
    assignments: List[ScheduledTask] = field(default_factory=list)
    makespan:    float               = 0.0
    total_cost:  float               = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schedule":
        return cls(
            assignments = [ScheduledTask.from_dict(a) for a in data.get("assignments", [])],
            makespan    = float(data.get("makespan", 0.0)),
            total_cost  = float(data.get("total_cost", 0.0)),
        )
