import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.algorithms.models import Task, Agent
from app.algorithms.scheduler import Scheduler
from app.algorithms.reoptimizer import Reoptimizer

def run_tests():
    print("Testing Scheduler and Reoptimizer...")
    tasks = [
        Task(id="t1", name="Task 1", required_skill="backend", est_time=5, est_cost=10, deps=[]),
        Task(id="t2", name="Task 2", required_skill="database", est_time=3, est_cost=5, deps=["t1"]),
        Task(id="t3", name="Task 3", required_skill="testing", est_time=4, est_cost=8, deps=["t1"])
    ]
    agents = [
        Agent(id="a1", name="Agent 1", skills=["backend", "database"], cost_per_unit=2, speed=1),
        Agent(id="a2", name="Agent 2", skills=["testing", "backend"], cost_per_unit=3, speed=1.2)
    ]
    
    scheduler = Scheduler()
    try:
        schedule = scheduler.greedy_schedule(tasks, agents)
        print("[PASS] Greedy Schedule Generated")
        print(f"Assignments: {len(schedule.assignments)}")  # <--- Yahan fix kiya gaya hai
        print(f"Makespan: {schedule.makespan}")
    except Exception as e:
        print(f"[FAIL] Scheduler error: {e}")
        return

    try:
        reopt = Reoptimizer()
        new_schedule = reopt.replan(tasks, agents, "agent_failed", {"agent_id": "a1"})
        print("[PASS] Reoptimizer works")
    except Exception as e:
        print(f"[FAIL] Reoptimizer error: {e}")
        return
        
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
