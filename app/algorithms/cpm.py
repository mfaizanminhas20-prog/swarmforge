"""
cpm.py  —  Critical Path Method (CPM) for SWARMFORGE.

Depends on:
    .graph   ->  DAG          (adjacency-list directed acyclic graph)
    .models  ->  Task         (dataclass with .id, .duration, .dependencies)
"""
from __future__ import annotations
from typing import List, Dict

from .graph  import DAG
from .models import Task


class CPM:
    """
    Computes the critical path of a task dependency graph.

    Parameters
    ----------
    tasks : list[Task]
        All tasks in the project.  Each task must expose:
            .id           – unique string identifier
            .duration     – numeric effort / time units  (>= 0)
            .dependencies – list[str] of predecessor task IDs

    Usage
    -----
    ::

        cpm  = CPM(tasks)
        path = cpm.compute_critical_path()   # list of task IDs
        info = cpm.get_timings()             # ES / EF / LS / LF per task
    """

    def __init__(self, tasks: List[Task]) -> None:
        self._tasks: Dict[str, Task] = {t.id: t for t in tasks}

        # Build the DAG from the existing graph module
        self._dag = DAG()
        for task in tasks:
            self._dag.add_node(task.id)
        for task in tasks:
            for dep in task.dependencies:
                if dep in self._tasks:
                    # Edge direction:  predecessor  -->  successor
                    self._dag.add_edge(dep, task.id)

        # Results populated by compute_critical_path()
        self._es:    Dict[str, float] = {}
        self._ef:    Dict[str, float] = {}
        self._ls:    Dict[str, float] = {}
        self._lf:    Dict[str, float] = {}
        self._float: Dict[str, float] = {}
        self._critical_path: List[str] = []
        self._computed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_critical_path(self) -> List[str]:
        """
        Run the forward and backward passes and return the critical path.

        The critical path is the ordered sequence of tasks whose
        total float (LS - ES) equals zero — i.e. any delay on these
        tasks delays the entire project.

        Returns
        -------
        list[str]
            Task IDs in topological order that lie on the critical path.
        """
        if self._computed:
            return self._critical_path

        order = self._dag.topological_sort()   # raises if cycle detected

        # ── Forward pass (ES / EF) ────────────────────────────────────
        for tid in order:
            task = self._tasks[tid]
            predecessors = [
                dep for dep in task.dependencies
                if dep in self._tasks
            ]
            if predecessors:
                self._es[tid] = max(self._ef[p] for p in predecessors)
            else:
                self._es[tid] = 0.0

            self._ef[tid] = self._es[tid] + task.duration

        # Project makespan = latest EF across all tasks
        makespan: float = max(self._ef.values(), default=0.0)

        # ── Backward pass (LS / LF) ───────────────────────────────────
        # Build a successor map so we can walk backwards
        successors: Dict[str, List[str]] = {tid: [] for tid in self._tasks}
        for tid, task in self._tasks.items():
            for dep in task.dependencies:
                if dep in self._tasks:
                    successors[dep].append(tid)

        for tid in reversed(order):
            succs = successors[tid]
            if succs:
                self._lf[tid] = min(self._ls[s] for s in succs)
            else:
                # Sink node — latest finish equals project makespan
                self._lf[tid] = makespan

            self._ls[tid]    = self._lf[tid] - self._tasks[tid].duration
            # Guard against floating-point drift with a tight round
            self._float[tid] = round(self._ls[tid] - self._es[tid], 10)

        # ── Identify critical tasks (float == 0) ─────────────────────
        self._critical_path = [
            tid for tid in order
            if self._float[tid] == 0
        ]

        self._computed = True
        return self._critical_path

    def get_timings(self) -> Dict[str, Dict[str, float]]:
        """
        Return ES, EF, LS, LF, and float for every task.

        ``compute_critical_path()`` is called automatically if it has
        not been called yet.

        Returns
        -------
        dict[str, dict]  keyed by task ID, each value containing:
            earliest_start  / earliest_finish
            latest_start    / latest_finish
            float           (total slack; 0 ⟹ critical)
        """
        self.compute_critical_path()
        return {
            tid: {
                "earliest_start":  self._es[tid],
                "earliest_finish": self._ef[tid],
                "latest_start":    self._ls[tid],
                "latest_finish":   self._lf[tid],
                "float":           self._float[tid],
            }
            for tid in self._tasks
        }

    @property
    def makespan(self) -> float:
        """Minimum project duration derived from the forward pass."""
        self.compute_critical_path()
        return max(self._ef.values(), default=0.0)
