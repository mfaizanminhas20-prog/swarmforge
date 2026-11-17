from typing import List
from .models import Task, Agent, Schedule
from .scheduler import Scheduler

class Reoptimizer:
    def replan(self, tasks: List[Task], agents: List[Agent], event_type: str, event_data: dict) -> Schedule:
        if event_type == "agent_failed":
            failed_id = event_data.get("agent_id")
            for agent in agents:
                if agent.id == failed_id:
                    agent.available = False
                    agent.current_task = None
                    
        elif event_type == "task_added":
            new_task = event_data.get("task")
            if new_task: tasks.append(new_task)

        elif event_type == "task_delayed":
            tid = event_data.get("task_id")
            extra = event_data.get("extra_time", 0)
            for task in tasks:
                if task.id == tid:
                    task.est_time += extra

        remaining_tasks = [t for t in tasks if t.status != "done"]
        scheduler = Scheduler()
        return scheduler.greedy_schedule(remaining_tasks, agents)
