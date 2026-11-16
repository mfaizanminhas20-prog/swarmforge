from typing import List, Dict
from .models import Task, Agent, Schedule
from .scheduler import Scheduler

class Reoptimizer:
    def replan(self, tasks: List[Task], agents: List[Agent], event_type: str, event_data: dict) -> Schedule:
        # 1. Handle the event
        if event_type == "agent_failed":
            failed_agent_id = event_data.get("agent_id")
            for agent in agents:
                if agent.id == failed_agent_id:
                    agent.available = False
                    agent.current_task = None
                    
        elif event_type == "task_added":
            new_task = event_data.get("task")
            if new_task:
                tasks.append(new_task)

        elif event_type == "task_delayed":
            task_id = event_data.get("task_id")
            extra_time = event_data.get("extra_time", 0)
            for task in tasks:
                if task.id == task_id:
                    task.est_time += extra_time

        # 2. Filter out completed tasks
        remaining_tasks = [t for t in tasks if t.status != "done"]

        # 3. Re-run scheduler on remaining tasks and available agents
        scheduler = Scheduler()
        new_schedule = scheduler.greedy_schedule(remaining_tasks, agents)
        
        return new_schedule