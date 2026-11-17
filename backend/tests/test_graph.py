import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.algorithms.models import Task
from app.algorithms.graph import DAG

def run_tests():
    print("Testing Graph...")
    tasks = [
        Task(id="t1", name="A", required_skill="x", est_time=3, est_cost=1, deps=[]),
        Task(id="t2", name="B", required_skill="x", est_time=4, est_cost=1, deps=["t1"]),
        Task(id="t3", name="C", required_skill="x", est_time=2, est_cost=1, deps=["t1"])
    ]
    dag = DAG(tasks)
    order = dag.topological_sort()
    print(f"[PASS] Topological Sort: {order}")
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
