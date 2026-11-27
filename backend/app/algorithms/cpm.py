from typing import List, Dict
from .graph import DAG
from .models import Task

class CPM:
    def __init__(self, tasks: List[Task]):
        self._tasks: Dict[str, Task] = {t.id: t for t in tasks}
        self._dag = DAG(tasks)
        self._es, self._ef, self._ls, self._lf, self._float = {}, {}, {}, {}, {}
        self._critical_path = []
        self._computed = False

    def compute_critical_path(self) -> List[str]:
        if self._computed: return self._critical_path
        order = self._dag.topological_sort()

        for tid in order:
            task = self._tasks[tid]
            self._es[tid] = max((self._ef[p] for p in task.deps), default=0.0)
            self._ef[tid] = self._es[tid] + task.est_time

        makespan = max(self._ef.values(), default=0.0)
        successors = {tid: [] for tid in self._tasks}
        for tid, task in self._tasks.items():
            for dep in task.deps:
                if dep in successors: successors[dep].append(tid)

        for tid in reversed(order):
            self._lf[tid] = min((self._ls[s] for s in successors[tid]), default=makespan)
            self._ls[tid] = self._lf[tid] - self._tasks[tid].est_time
            self._float[tid] = round(self._ls[tid] - self._es[tid], 10)

        self._critical_path = [tid for tid in order if self._float[tid] == 0]
        self._computed = True
        return self._critical_path

    @property
    def makespan(self) -> float:
        self.compute_critical_path()
        return max(self._ef.values(), default=0.0)

    def get_details(self) -> dict[str, dict]:
        if not self._computed:
            self.compute_critical_path()
        critical_set = set(self._critical_path)
        return {
            tid: {
                "es": float(self._es[tid]),
                "ef": float(self._ef[tid]),
                "ls": float(self._ls[tid]),
                "lf": float(self._lf[tid]),
                "float": float(self._float[tid]),
                "critical": tid in critical_set,
            }
            for tid in self._tasks
        }
