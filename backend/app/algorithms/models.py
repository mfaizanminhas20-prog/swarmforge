from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Task:
    id: str
    name: str
    required_skill: str
    est_time: float
    est_cost: float
    priority: str = "medium"
    deps: List[str] = field(default_factory=list)
    status: str = "blocked"

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(id=d["id"], name=d["name"], required_skill=d["required_skill"], est_time=float(d["est_time"]), est_cost=float(d["est_cost"]), priority=d.get("priority", "medium"), deps=list(d.get("deps", [])), status=d.get("status", "blocked"))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "required_skill": self.required_skill, "est_time": self.est_time, "est_cost": self.est_cost, "priority": self.priority, "deps": self.deps, "status": self.status}

@dataclass
class Agent:
    id: str
    name: str
    skills: List[str]
    speed: float = 1.0
    cost_per_unit: float = 1.0
    available: bool = True
    current_task: Optional[str] = None

    def can_do(self, task: Task) -> bool:
        return task.required_skill in self.skills

    @classmethod
    def from_dict(cls, d: dict) -> "Agent":
        return cls(id=d["id"], name=d["name"], skills=list(d["skills"]), speed=float(d.get("speed", 1.0)), cost_per_unit=float(d.get("cost_per_unit", 1.0)), available=bool(d.get("available", True)), current_task=d.get("current_task"))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "skills": self.skills, "speed": self.speed, "cost_per_unit": self.cost_per_unit, "available": self.available, "current_task": self.current_task}

@dataclass
class ScheduledTask:
    task_id: str
    agent_id: str
    start_time: float
    end_time: float
    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "agent_id": self.agent_id, "start_time": self.start_time, "end_time": self.end_time}

@dataclass
class Schedule:
    assignments: List[ScheduledTask] = field(default_factory=list)
    makespan: float = 0.0
    total_cost: float = 0.0
    def to_dict(self) -> dict:
        return {"assignments": [a.to_dict() for a in self.assignments], "makespan": self.makespan, "total_cost": self.total_cost}
