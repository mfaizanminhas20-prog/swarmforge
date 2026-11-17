from typing import List
from .models import Task, Agent, ScheduledTask, Schedule
from .graph import DAG

class Scheduler:
    def greedy_schedule(self, tasks: List[Task], agents: List[Agent]) -> Schedule:
        dag = DAG(tasks)
        completed = set()
        running_tasks = {} 
        assignments = []
        current_time = 0.0
        
        while len(completed) < len(tasks):
            ready_task_ids = dag.get_ready_tasks(completed)
            assigned_task_ids = {a.task_id for a in assignments}
            available_tasks = [dag.tasks[tid] for tid in ready_task_ids if tid not in assigned_task_ids]
            
            priority_map = {"high": 3, "medium": 2, "low": 1}
            available_tasks.sort(key=lambda t: priority_map.get(t.priority, 2), reverse=True)

            for task in available_tasks:
                best_agent = None
                best_score = -1.0
                
                for agent in agents:
                    if not agent.available or agent.id in running_tasks or not agent.can_do(task):
                        continue
                    # Score: speed is good, cost is bad. 
                    score = agent.speed / (agent.cost_per_unit + 0.1)
                    if score > best_score:
                        best_score = score
                        best_agent = agent
                
                if best_agent:
                    actual_time = task.est_time / best_agent.speed
                    end_time = current_time + actual_time
                    
                    running_tasks[best_agent.id] = (task.id, end_time)
                    best_agent.current_task = task.id
                    
                    assignments.append(ScheduledTask(task_id=task.id, agent_id=best_agent.id, start_time=current_time, end_time=end_time))

            if running_tasks:
                current_time = min(end_t for _, end_t in running_tasks.values())
                finished_agents = [aid for aid, (_, end_t) in running_tasks.items() if end_t <= current_time]
                for aid in finished_agents:
                    task_id, _ = running_tasks.pop(aid)
                    completed.add(task_id)
                    for agent in agents:
                        if agent.id == aid:
                            agent.current_task = None
            else:
                if not available_tasks: break # Deadlock protection

        makespan = max((a.end_time for a in assignments), default=0.0)
        total_cost = sum(dag.tasks[a.task_id].est_cost for a in assignments)
        return Schedule(assignments=assignments, makespan=makespan, total_cost=total_cost)
