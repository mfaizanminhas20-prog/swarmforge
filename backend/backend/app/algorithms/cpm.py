"""
cpm.py  —  Critical Path Method for SWARMFORGE.
"""
from __future__ import annotations
from typing import List, Dict, Any

from .models import Task


class CPM:
    """
    Computes the critical path of a task DAG.

    Parameters
    ----------
    tasks : list of Task (or plain dicts — both accepted)
    """

    def __init__(self, tasks: List[Any]):
        # Accept both Task dataclasses and raw dicts
        self._tasks: Dict[str, Task] = {}
        for t in tasks:
            if isinstance(t, dict):
                t = Task.from_dict(t)
            self._tasks[t.id] = t

        self._es:    Dict[str, float] = {}
        self._ef:    Dict[str, float] = {}
        self._ls:    Dict[str, float] = {}
        self._lf:    Dict[str, float] = {}
        self._float: Dict[str, float] = {}
        self._order: List[str]        = []
        self._done                    = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _topo_sort(self) -> List[str]:
        in_degree: Dict[str, int]       = {tid: 0 for tid in self._tasks}
        children:  Dict[str, List[str]] = {tid: [] for tid in self._tasks}

        for tid, task in self._tasks.items():
            for dep in task.dependencies:
                if dep in self._tasks:
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

        if len(order) != len(self._tasks):
            raise ValueError("Cycle detected — CPM requires a DAG.")
        return order

    def _run(self) -> None:
        if self._done:
            return

        self._order = self._topo_sort()

        # Forward pass
        for tid in self._order:
            task = self._tasks[tid]
            deps = [d for d in task.dependencies if d in self._tasks]
            self._es[tid] = max((self._ef[d] for d in deps), default=0.0)
            self._ef[tid] = self._es[tid] + task.duration

        makespan = max(self._ef.values(), default=0.0)

        # Successor map
        successors: Dict[str, List[str]] = {tid: [] for tid in self._tasks}
        for tid, task in self._tasks.items():
            for dep in task.dependencies:
                if dep in self._tasks:
                    successors[dep].append(tid)

        # Backward pass
        for tid in reversed(self._order):
            task = self._tasks[tid]
            succs = successors[tid]
            self._lf[tid] = min((self._ls[s] for s in succs), default=makespan)
            self._ls[tid] = self._lf[tid] - task.duration
            self._float[tid] = round(self._ls[tid] - self._es[tid], 10)

        self._done = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compute_critical_path(self) -> List[str]:
        """Return the ordered list of task IDs whose total float == 0."""
        self._run()
        return [tid for tid in self._order if self._float[tid] == 0]

    @property
    def makespan(self) -> float:
        self._run()
        return max(self._ef.values(), default=0.0)

    def get_task_timings(self) -> Dict[str, Dict[str, float]]:
        """
        Return ES, EF, LS, LF, and float for every task.
        """
        self._run()
        return {
            tid: {
                "earliest_start":  self._es[tid],
                "earliest_finish": self._ef[tid],
                "latest_start":    self._ls[tid],
                "latest_finish":   self._lf[tid],
                "float":           self._float[tid],
            }
            for tid in self._order
        }
