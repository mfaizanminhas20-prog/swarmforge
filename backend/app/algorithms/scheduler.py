from typing import List, Dict
from .models import Task, Agent, ScheduledTask, Schedule
from .graph import DAG

class Scheduler:
    def greedy_schedule(self, tasks: List[Task], agents: List[Agent], constraints: dict = None) -> Schedule:
        dag = DAG(tasks)
        order = dag.topological_sort()
        
        completed = set()
        running_tasks = {} # agent_id -> end_time
        assignments = []
        current_time = 0.0
        
        while len(completed) < len(tasks):
            # Find ready tasks
            ready_task_ids = dag.get_ready_tasks(completed)
            
            # Sort ready tasks by priority (high first)
            priority_map = {"high": 3, "medium": 2, "low": 1}
            ready_tasks = sorted([dag.tasks[tid] for tid in ready_task_ids], 
                                 key=lambda t: priority_map.get(t.priority, 2), reverse=True)
            
            if not ready_tasks:
                # If no ready tasks but some are running, advance time
                if running_tasks:
                    current_time = min(running_tasks.values())
                    for aid, end_t in list(running_tasks.items()):
                        if end_t <= current_time:
                            del running_tasks[aid]
                    continue
                else:
                    break # Deadlock or cycle (should be caught earlier)

            for task in ready_tasks:
                if task.id in completed or any(a.task_id == task.id for a in assignments):
                    continue
                    
                # Find best agent
                best_agent = None
                best_score = -1.0
                
                for agent in agents:
                    if not agent.available:
                        continue
                    if agent.id in running_tasks:
                        continue
                    if not agent.can_do(task):
                        continue
                        
                    # Score = speed / cost
                    score = agent.speed / (agent.cost_per_unit + 0.1)
                    if score > best_score:
                        best_score = score
                        best_agent = agent
                
                if best_agent:
                    start_time = current_time
                    # Agent speed affects time
                    actual_time = task.est_time / best_agent.speed
                    end_time = start_time + actual_time
                    
                    running_tasks[best_agent.id] = end_time
                    best_agent.current_task = task.id
                    
                    assignments.append(ScheduledTask(
                        task_id=task.id,
                        agent_id=best_agent.id,
                        start_time=start_time,
                        end_time=end_time
                    ))
            
            # Advance time to next completion
            if running_tasks:
                current_time = min(running_tasks.values())
                finished_agents = [aid for aid, end_t in running_tasks.items() if end_t <= current_time]
                for aid in finished_agents:
                    del running_tasks[aid]
                    # Mark task completed
                    for a in assignments:
                        if a.agent_id == aid and a.end_time <= current_time:
                            completed.add(a.task_id)
                            # Reset agent
                            for agent in agents:
                                if agent.id == aid:
                                    agent.current_task = None
            else:
                # In case no tasks are running but not all completed, advance slightly
                current_time += 1.0

        makespan = max((a.end_time for a in assignments), default=0.0)
        total_cost = sum(dag.tasks[a.task_id].est_cost for a in assignments)
        
        return Schedule(assignments=assignments, makespan=makespan, total_cost=total_cost)

    def fcfs_schedule(self, tasks: List[Task], agents: List[Agent]) -> Schedule:
        # Simple sequential fallback
        current_time = 0.0
        assignments = []
        dag = DAG(tasks)
        order = dag.topological_sort()
        
        for tid in order:
            task = dag.tasks[tid]
            best_agent = next((a for a in agents if a.can_do(task)), agents[0] if agents else None)
            if not best_agent:
                continue
            actual_time = task.est_time / best_agent.speed
            assignments.append(ScheduledTask(task_id=tid, agent_id=best_agent.id, start_time=current_time, end_time=current_time + actual_time))
            current_time += actual_time
            
        makespan = current_time
        total_cost = sum(dag.tasks[a.task_id].est_cost for a in assignments)
        return Schedule(assignments=assignments, makespan=makespan, total_cost=total_cost)
