import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.algorithms.models import Task
from app.algorithms.cpm import CPM


def get_sample_tasks() -> list[Task]:
    return [
        Task(id="t1", name="A", required_skill="x", est_time=3, est_cost=1, deps=[]),
        Task(id="t2", name="B", required_skill="x", est_time=4, est_cost=1, deps=["t1"]),
        Task(id="t3", name="C", required_skill="x", est_time=2, est_cost=1, deps=["t1"]),
        Task(id="t4", name="D", required_skill="x", est_time=1, est_cost=1, deps=["t2", "t3"]),
    ]


def test_cpm_get_details_4_task_example():
    tasks = get_sample_tasks()
    cpm = CPM(tasks)

    # get_details should compute critical path automatically if not already computed
    details = cpm.get_details()

    assert set(details.keys()) == {"t1", "t2", "t3", "t4"}

    # Critical path tasks: t1 -> t2 -> t4
    critical_task_ids = ["t1", "t2", "t4"]
    for tid in critical_task_ids:
        assert details[tid]["float"] == 0.0, f"Expected float 0 for critical task {tid}, got {details[tid]['float']}"
        assert details[tid]["critical"] is True, f"Expected critical == True for task {tid}"

    # Non-critical tasks: t3
    non_critical_task_ids = ["t3"]
    for tid in non_critical_task_ids:
        assert details[tid]["float"] > 0, f"Expected float > 0 for non-critical task {tid}, got {details[tid]['float']}"
        assert details[tid]["critical"] is False, f"Expected critical == False for task {tid}"

    # Verify exact timing numbers
    assert details["t1"] == {"es": 0.0, "ef": 3.0, "ls": 0.0, "lf": 3.0, "float": 0.0, "critical": True}
    assert details["t2"] == {"es": 3.0, "ef": 7.0, "ls": 3.0, "lf": 7.0, "float": 0.0, "critical": True}
    assert details["t3"] == {"es": 3.0, "ef": 5.0, "ls": 5.0, "lf": 7.0, "float": 2.0, "critical": False}
    assert details["t4"] == {"es": 7.0, "ef": 8.0, "ls": 7.0, "lf": 8.0, "float": 0.0, "critical": True}


def test_cpm_get_details_after_compute_critical_path():
    tasks = get_sample_tasks()
    cpm = CPM(tasks)
    path = cpm.compute_critical_path()
    assert path == ["t1", "t2", "t4"]

    details = cpm.get_details()
    for tid in path:
        assert details[tid]["float"] == 0.0
        assert details[tid]["critical"] is True

    assert details["t3"]["float"] > 0
    assert details["t3"]["critical"] is False


def run_tests():
    test_cpm_get_details_4_task_example()
    test_cpm_get_details_after_compute_critical_path()
    print("[PASS] CPM get_details tests passed successfully.")


if __name__ == "__main__":
    run_tests()
