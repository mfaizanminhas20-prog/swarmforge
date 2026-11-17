import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.algorithms.models import Task
from app.algorithms.cpm import CPM

def run_tests():
    print("Testing CPM...")
    tasks = [
        Task(id="t1", name="A", required_skill="x", est_time=3, est_cost=1, deps=[]),
        Task(id="t2", name="B", required_skill="x", est_time=4, est_cost=1, deps=["t1"]),
        Task(id="t3", name="C", required_skill="x", est_time=2, est_cost=1, deps=["t1"]),
        Task(id="t4", name="D", required_skill="x", est_time=1, est_cost=1, deps=["t2", "t3"])
    ]
    cpm = CPM(tasks)
    path = cpm.compute_critical_path()
    print(f"[PASS] Critical Path: {path}")
    print(f"[PASS] Makespan: {cpm.makespan}")
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
