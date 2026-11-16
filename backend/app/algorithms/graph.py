from collections import defaultdict, deque
from typing import Dict, List, Set
from .models import Task

class CycleError(Exception):
    pass

class DAG:
    def __init__(self, tasks: List[Task]):
        self.tasks: Dict[str, Task] = {t.id: t for t in tasks}
        self.adj: Dict[str, List[str]] = defaultdict(list)
        self.rev: Dict[str, List[str]] = defaultdict(list)
        for task in tasks:
            for dep in task.deps:
                self.adj[dep].append(task.id)
                self.rev[task.id].append(dep)

    def topological_sort(self) -> List[str]:
        in_degree = {tid: len(self.rev[tid]) for tid in self.tasks}
        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        order = []
        while queue:
            tid = queue.popleft()
            order.append(tid)
            for succ in self.adj[tid]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)
        if len(order) != len(self.tasks):
            raise CycleError("Cycle detected")
        return order

    def get_ready_tasks(self, completed: Set[str]) -> List[str]:
        return [tid for tid, task in self.tasks.items() if tid not in completed and task.status != "running" and all(dep in completed for dep in task.deps)]
