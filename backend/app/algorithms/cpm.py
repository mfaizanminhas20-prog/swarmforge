"""
cpm.py - Critical Path Method (CPM) for SWARMFORGE
Calculates the minimum project makespan and identifies the critical path.
"""
from typing import List, Dict, Any


class CPM:
    """
    Implements the Critical Path Method (CPM) algorithm.

    Given a list of task dicts with keys:
        - id       : unique task identifier
        - duration : how long the task takes
        - dependencies: list of task IDs that must complete before this task

    Computes:
        - Earliest Start  (ES)
        - Earliest Finish (EF)
        - Latest Start    (LS)
        - Latest Finish   (LF)
        - Float / Slack   (LS - ES)
        - Critical Path   (all tasks with zero float)
    """

    def __init__(self, tasks: List[Dict[str, Any]]):
        self.tasks: Dict[str, Dict[str, Any]] = {t["id"]: t for t in tasks}
        self._schedule: Dict[str, Dict[str, float]] = {}
        self._order: List[str] = []
        self._computed = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _topological_sort(self) -> List[str]:
        """Return task IDs in topological order using Kahn's algorithm."""
        in_degree: Dict[str, int] = {tid: 0 for tid in self.tasks}
        children: Dict[str, List[str]] = {tid: [] for tid in self.tasks}

        for tid, task in self.tasks.items():
            for dep in task.get("dependencies", []):
                if dep in self.tasks:
                    in_degree[tid] += 1
                    children[dep].append(tid)

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for child in children[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.tasks):
            raise ValueError("Cycle detected in task dependencies — CPM requires a DAG.")

        return order

    def _compute(self):
        """Run the forward and backward passes."""
        if self._computed:
            return

        self._order = self._topological_sort()
        sched = {}

        # --- Forward pass (ES / EF) ---
        for tid in self._order:
            task = self.tasks[tid]
            deps = task.get("dependencies", [])
            es = max((sched[d]["ef"] for d in deps if d in sched), default=0.0)
            ef = es + task.get("duration", 0)
            sched[tid] = {"es": es, "ef": ef, "ls": 0.0, "lf": 0.0, "float": 0.0}

        # Project makespan = max EF across all tasks
        makespan = max(v["ef"] for v in sched.values()) if sched else 0.0

        # Build reverse adjacency for the backward pass
        parents: Dict[str, List[str]] = {tid: [] for tid in self.tasks}
        for tid, task in self.tasks.items():
            for dep in task.get("dependencies", []):
                if dep in self.tasks:
                    parents[tid].append(dep)   # dep → tid, so tid's parent is dep

        # Successor map: which tasks come AFTER a given task
        successors: Dict[str, List[str]] = {tid: [] for tid in self.tasks}
        for tid, task in self.tasks.items():
            for dep in task.get("dependencies", []):
                if dep in self.tasks:
                    successors[dep].append(tid)

        # --- Backward pass (LS / LF) ---
        for tid in reversed(self._order):
            task = self.tasks[tid]
            succs = successors[tid]
            if not succs:
                lf = makespan
            else:
                lf = min(sched[s]["ls"] for s in succs)
            ls = lf - task.get("duration", 0)
            sched[tid]["lf"] = lf
            sched[tid]["ls"] = ls
            sched[tid]["float"] = round(ls - sched[tid]["es"], 10)  # floating-point guard

        self._schedule = sched
        self._computed = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_critical_path(self) -> List[str]:
        """
        Return the ordered list of task IDs on the critical path
        (tasks whose total float == 0).
        """
        self._compute()
        return [tid for tid in self._order if self._schedule[tid]["float"] == 0]

    def compute_earliest_latest(self) -> Dict[str, Dict[str, float]]:
        """
        Return a dict keyed by task ID containing:
            es   - Earliest Start
            ef   - Earliest Finish
            ls   - Latest Start
            lf   - Latest Finish
            float- Total Float (slack)
        """
        self._compute()
        return {
            tid: {
                "earliest_start":  v["es"],
                "earliest_finish": v["ef"],
                "latest_start":    v["ls"],
                "latest_finish":   v["lf"],
                "float":           v["float"],
            }
            for tid, v in self._schedule.items()
        }

    @property
    def makespan(self) -> float:
        """Minimum project duration (length of the critical path)."""
        self._compute()
        return max((v["ef"] for v in self._schedule.values()), default=0.0)
