"""
test_scheduler.py  —  Automated tests for SWARMFORGE core algorithms.
Run with:  python -m tests.test_scheduler   (from the backend/ directory)
"""
import sys
import os

# Allow  'python -m tests.test_scheduler'  from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.models      import Task, Agent, Schedule, ScheduledTask
from app.algorithms.scheduler   import Scheduler
from app.algorithms.reoptimizer import Reoptimizer
from app.algorithms.cpm         import CPM


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_tasks():
    return [
        Task(id="T1", duration=3, priority=2, dependencies=[]),
        Task(id="T2", duration=2, priority=1, dependencies=["T1"]),
        Task(id="T3", duration=4, priority=3, dependencies=["T1"]),
        Task(id="T4", duration=1, priority=2, dependencies=["T2", "T3"]),
    ]


def make_agents():
    return [
        Agent(id="A1", speed=2.0, cost_per_unit=1.0, available=True),
        Agent(id="A2", speed=1.0, cost_per_unit=0.5, available=True),
        Agent(id="A3", speed=3.0, cost_per_unit=2.0, available=True),
    ]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert(condition: bool, message: str) -> None:
    if not condition:
        print(f"[FAIL] {message}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# TEST 1 — Greedy schedule returns a Schedule with all tasks assigned
# ---------------------------------------------------------------------------
def test_greedy_schedule():
    scheduler = Scheduler()
    tasks     = make_tasks()
    agents    = make_agents()
    schedule  = scheduler.greedy_schedule(tasks, agents)

    _assert(isinstance(schedule, Schedule),
            "greedy_schedule must return a Schedule object")
    _assert(len(schedule.assignments) == 4,
            f"Expected 4 assignments, got {len(schedule.assignments)}")
    _assert(schedule.makespan > 0,
            f"Makespan must be > 0, got {schedule.makespan}")
    _assert(schedule.total_cost > 0,
            f"total_cost must be > 0, got {schedule.total_cost}")

    # Dependency check: T2 and T3 must start after T1 ends
    by_task = {a.task_id: a for a in schedule.assignments}
    t1_end  = by_task["T1"].end_time
    _assert(by_task["T2"].start_time >= t1_end,
            "T2 must start after T1 finishes")
    _assert(by_task["T3"].start_time >= t1_end,
            "T3 must start after T1 finishes")
    t2_end  = by_task["T2"].end_time
    t3_end  = by_task["T3"].end_time
    _assert(by_task["T4"].start_time >= max(t2_end, t3_end),
            "T4 must start after both T2 and T3 finish")

    print("[PASS] test_greedy_schedule")


# ---------------------------------------------------------------------------
# TEST 2 — FCFS schedule produces a valid Schedule
# ---------------------------------------------------------------------------
def test_fcfs_schedule():
    scheduler = Scheduler()
    tasks     = make_tasks()
    agents    = make_agents()
    schedule  = scheduler.fcfs_schedule(tasks, agents)

    _assert(isinstance(schedule, Schedule),
            "fcfs_schedule must return a Schedule object")
    _assert(len(schedule.assignments) == 4,
            f"FCFS expected 4 assignments, got {len(schedule.assignments)}")
    _assert(schedule.makespan > 0,
            f"FCFS makespan must be > 0, got {schedule.makespan}")

    print("[PASS] test_fcfs_schedule")


# ---------------------------------------------------------------------------
# TEST 3 — Reoptimizer handles agent_failed event
# ---------------------------------------------------------------------------
def test_reoptimizer_agent_failed():
    reopt  = Reoptimizer()
    tasks  = make_tasks()
    agents = make_agents()   # A1, A2, A3

    # Fail agent A1 — schedule should use only A2 and A3
    schedule = reopt.replan(
        tasks      = tasks,
        agents     = agents,
        event_type = "agent_failed",
        event_data = {"agent_id": "A1"},
    )

    _assert(isinstance(schedule, Schedule),
            "replan must return a Schedule object")
    _assert(len(schedule.assignments) == 4,
            f"Expected 4 assignments after replan, got {len(schedule.assignments)}")

    used_agents = {a.agent_id for a in schedule.assignments}
    _assert("A1" not in used_agents,
            f"A1 is failed — should not appear in schedule, but found: {used_agents}")

    print("[PASS] test_reoptimizer_agent_failed")


# ---------------------------------------------------------------------------
# TEST 4 — Reoptimizer handles task_added event
# ---------------------------------------------------------------------------
def test_reoptimizer_task_added():
    reopt  = Reoptimizer()
    tasks  = make_tasks()
    agents = make_agents()

    new_task_dict = {
        "id":           "T5",
        "duration":     2,
        "priority":     3,
        "dependencies": ["T4"],
    }

    schedule = reopt.replan(
        tasks      = tasks,
        agents     = agents,
        event_type = "task_added",
        event_data = {"task": new_task_dict},
    )

    _assert(isinstance(schedule, Schedule),
            "replan must return a Schedule object after task_added")
    _assert(len(schedule.assignments) == 5,
            f"Expected 5 assignments after adding T5, got {len(schedule.assignments)}")

    task_ids = {a.task_id for a in schedule.assignments}
    _assert("T5" in task_ids,
            "Newly added task T5 must appear in the schedule")

    print("[PASS] test_reoptimizer_task_added")


# ---------------------------------------------------------------------------
# TEST 5 — CPM identifies the correct critical path
# ---------------------------------------------------------------------------
def test_cpm():
    tasks = make_tasks()
    cpm   = CPM(tasks)
    cp    = cpm.compute_critical_path()

    _assert(isinstance(cp, list) and len(cp) > 0,
            "compute_critical_path must return a non-empty list")

    # Critical path must start at T1
    _assert(cp[0] == "T1",
            f"Critical path must start with T1, got: {cp}")
    # T3 (duration=4) is longer than T2 (duration=2), so path goes through T3
    _assert("T3" in cp,
            f"T3 (longest branch) must be on the critical path, got: {cp}")
    # Must end at T4
    _assert(cp[-1] == "T4",
            f"Critical path must end with T4, got: {cp}")

    # Makespan sanity: T1(3) + T3(4) + T4(1) = 8
    _assert(cpm.makespan == 8.0,
            f"Expected makespan 8.0, got {cpm.makespan}")

    print("[PASS] test_cpm")


# ---------------------------------------------------------------------------
# TEST 6 — ScheduledTask and Schedule from_dict round-trips
# ---------------------------------------------------------------------------
def test_model_from_dict():
    st = ScheduledTask.from_dict({
        "task_id": "T1", "agent_id": "A1",
        "start_time": 0.0, "end_time": 3.0,
    })
    _assert(st.task_id == "T1" and st.end_time == 3.0,
            "ScheduledTask.from_dict failed round-trip")

    sc = Schedule.from_dict({
        "assignments": [
            {"task_id": "T1", "agent_id": "A1", "start_time": 0.0, "end_time": 3.0}
        ],
        "makespan":   3.0,
        "total_cost": 3.0,
    })
    _assert(len(sc.assignments) == 1 and sc.makespan == 3.0,
            "Schedule.from_dict failed round-trip")

    print("[PASS] test_model_from_dict")


# ---------------------------------------------------------------------------
# TEST 7 — Greedy handles no available agents gracefully
# ---------------------------------------------------------------------------
def test_greedy_no_agents():
    scheduler = Scheduler()
    tasks     = make_tasks()
    agents    = [Agent(id="A1", speed=1, cost_per_unit=1, available=False)]
    schedule  = scheduler.greedy_schedule(tasks, agents)

    _assert(isinstance(schedule, Schedule),
            "greedy_schedule must still return a Schedule when no agents are available")
    _assert(len(schedule.assignments) == 0,
            "No assignments expected when all agents are unavailable")
    _assert(schedule.makespan == 0.0,
            "Makespan must be 0.0 when no agents are available")

    print("[PASS] test_greedy_no_agents")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 52)
    print("  SWARMFORGE — Core Algorithm Test Suite")
    print("=" * 52)

    test_greedy_schedule()
    test_fcfs_schedule()
    test_reoptimizer_agent_failed()
    test_reoptimizer_task_added()
    test_cpm()
    test_model_from_dict()
    test_greedy_no_agents()

    print()
    print("=" * 52)
    print("  ALL TESTS PASSED!")
    print("=" * 52)
