import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.algorithms.graph import DAG
from app.algorithms.models import Task

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "rest_api.json")

def test_topological_sort():
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    tasks = [Task.from_dict(t) for t in data["tasks"]]
    dag = DAG(tasks)
    order = dag.topological_sort()
    assert len(order) == len(tasks)
    print("[PASS] topological_sort:", order)

if __name__ == "__main__":
    test_topological_sort()
    print("ALL TESTS PASSED")
