"""
Execution Engine for SWARMFORGE missions.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from typing import Any, Callable, Dict, List, Literal, Optional, Set

from app.algorithms.cpm import CPM
from app.algorithms.graph import DAG, CycleError
from app.algorithms.models import Agent, Schedule, ScheduledTask, Task
from app.algorithms.reoptimizer import ReOptimizer
from app.algorithms.scheduler import GreedyScheduler
from app.exceptions import Conflict, NotFound, ValidationError
from app.state import MissionState, SimClock

logger = logging.getLogger(__name__)

__all__ = [
    "Engine",
    "NotFound",
    "Conflict",
    "ValidationError",
]


class Engine:
    """
    SWARMFORGE Async Execution Engine.

    Coordinates agent workers, simulated tick progression, event logging,
    concurrency locks, and dynamic replanning.
    """

    def __init__(
        self,
        state: MissionState,
        clock: Optional[SimClock] = None,
        scheduler: Optional[GreedyScheduler] = None,
        reoptimizer: Optional[ReOptimizer] = None,
        tick_duration: Optional[float] = None,
    ) -> None:
        self.state: MissionState = state
        self.clock: SimClock = clock if clock is not None else SimClock()
        self.scheduler: GreedyScheduler = (
            scheduler if scheduler is not None else GreedyScheduler()
        )
        self.reoptimizer: ReOptimizer = (
            reoptimizer if reoptimizer is not None else ReOptimizer(self.scheduler)
        )

        if tick_duration is not None:
            self.tick_duration: float = float(tick_duration)
        else:
            env_tick = os.getenv("SWARM_TICK_DURATION")
            self.tick_duration = float(env_tick) if env_tick is not None else 0.1

        if self.tick_duration <= 0:
            raise ValueError(f"tick_duration must be positive, got {self.tick_duration}")

        self._lock: asyncio.Lock = asyncio.Lock()
        self._seq: int = 1

        self._agent_queues: Dict[str, List[str]] = {aid: [] for aid in self.state.agents}
        self._wake_events: Dict[str, asyncio.Event] = {
            aid: asyncio.Event() for aid in self.state.agents
        }
        self._worker_tasks: Dict[str, asyncio.Task[None]] = {}
        self._task_spent_work: Dict[str, float] = {}
        self._task_done_events: Dict[str, asyncio.Event] = {
            tid: asyncio.Event() for tid in self.state.tasks
        }
        self.done_event: asyncio.Event = asyncio.Event()

        self.agent_status: Dict[str, Literal["idle", "busy", "dead"]] = {
            aid: "idle" for aid in self.state.agents
        }
        self.tasks_done: Dict[str, int] = {aid: 0 for aid in self.state.agents}
        self._listeners: List[Callable[[Dict[str, Any]], Any]] = []
        self._max_budget: Optional[float] = None

        # Initialize per-agent operational fields
        for agent in self.state.agents.values():
            agent.current_task = None
            agent.available = True
            setattr(agent, "status", "idle")
            setattr(agent, "tasks_done", 0)

    @classmethod
    def from_dict(
        cls,
        d: Dict[str, Any],
        mission_id: str = "mission-1",
        clock: Optional[SimClock] = None,
        tick_duration: Optional[float] = None,
    ) -> "Engine":
        """Instantiate Engine from a mission dictionary."""
        tasks = {t["id"]: Task.from_dict(t) for t in d.get("tasks", [])}
        agents = {a["id"]: Agent.from_dict(a) for a in d.get("agents", [])}
        state = MissionState(
            mission_id=mission_id,
            mission=d.get("mission", "Mission"),
            tasks=tasks,
            agents=agents,
        )
        return cls(state=state, clock=clock, tick_duration=tick_duration)

    @classmethod
    def from_fixture(
        cls,
        fixture_path: str,
        mission_id: str = "mission-1",
        clock: Optional[SimClock] = None,
        tick_duration: Optional[float] = None,
    ) -> "Engine":
        """Instantiate Engine from a JSON fixture file."""
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, mission_id=mission_id, clock=clock, tick_duration=tick_duration)

    def add_event_listener(self, listener: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a subscriber callback for emitted engine events."""
        self._listeners.append(listener)

    def emit(self, event_type: str, **payload: Any) -> Dict[str, Any]:
        """
        Emit a typed runtime event.

        Assigns monotonic integer seq and current simulated time t,
        then appends to the state event log.
        """
        event: Dict[str, Any] = {
            "seq": self._seq,
            "type": event_type,
            "t": self.clock.now(),
            **payload,
        }
        self._seq += 1
        self.state.event_log.append(event)

        for listener in self._listeners:
            try:
                res = listener(event)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as ex:
                logger.exception("Error in event listener: %s", ex)

        return event

    def _create_initial_plan_locked(self) -> Schedule:
        """Compute the initial greedy schedule and emit plan_created (caller must hold _lock)."""
        tasks = list(self.state.tasks.values())
        agents = [a for a in self.state.agents.values() if a.available and a.id not in self.state.dead]

        schedule = self.scheduler.greedy_schedule(tasks, agents)
        self.state.current_schedule = schedule

        cpm = CPM(tasks)
        cpm_details = cpm.get_details()

        self.emit(
            "plan_created",
            schedule=schedule.to_dict() if hasattr(schedule, "to_dict") else schedule,
            makespan=schedule.makespan,
            total_cost=schedule.total_cost,
            cpm_details=cpm_details,
            cpm=cpm_details,
        )

        for aid in self.state.agents:
            self._agent_queues[aid] = []

        # Sort assignments by start_time for ordering
        for assignment in sorted(schedule.assignments, key=lambda a: a.start_time):
            if assignment.agent_id in self._agent_queues:
                self._agent_queues[assignment.agent_id].append(assignment.task_id)

        return schedule

    async def create_initial_plan(self) -> Schedule:
        """Public method to compute and emit initial plan under lock."""
        async with self._lock:
            return self._create_initial_plan_locked()

    async def start(self, schedule: Optional[Schedule] = None) -> None:
        """Start the engine and launch all agent worker loops."""
        async with self._lock:
            if self.state.status == "running":
                return

            if schedule is not None:
                self.state.current_schedule = schedule
                tasks = list(self.state.tasks.values())
                cpm = CPM(tasks)
                cpm_details = cpm.get_details()
                self.emit(
                    "plan_created",
                    schedule=schedule.to_dict() if hasattr(schedule, "to_dict") else schedule,
                    makespan=schedule.makespan,
                    total_cost=schedule.total_cost,
                    cpm_details=cpm_details,
                    cpm=cpm_details,
                )
                for aid in self.state.agents:
                    self._agent_queues[aid] = []
                for assignment in sorted(schedule.assignments, key=lambda a: a.start_time):
                    if assignment.agent_id in self._agent_queues:
                        self._agent_queues[assignment.agent_id].append(assignment.task_id)
            elif self.state.current_schedule is None:
                self._create_initial_plan_locked()

            self.state.status = "running"
            self.emit("mission_started", mission_id=self.state.mission_id)

            # Spawn one worker task per agent
            for agent_id in self.state.agents:
                if agent_id not in self.state.dead:
                    self._worker_tasks[agent_id] = asyncio.create_task(
                        self._worker_loop(agent_id),
                        name=f"worker-{agent_id}",
                    )

            # Signal all wake events to start processing
            for ev in self._wake_events.values():
                ev.set()

    async def set_speed(self, multiplier: float) -> None:
        """
        Update the simulated speed multiplier.

        Validates 0.25 <= multiplier <= 4.0.
        """
        if not (0.25 <= multiplier <= 4.0):
            raise ValueError(f"Speed multiplier must be between 0.25 and 4.0, got {multiplier}")

        async with self._lock:
            self.clock.set_multiplier(multiplier)
            self.emit("speed_changed", multiplier=multiplier)

    async def finish(self) -> None:
        """Gracefully terminate engine execution and cancel workers."""
        async with self._lock:
            if self.state.status not in ("done", "failed"):
                self.state.status = "done"

            workers = list(self._worker_tasks.values())
            for task in workers:
                if not task.done():
                    task.cancel()

            for ev in self._wake_events.values():
                ev.set()

            for task in workers:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            self.done_event.set()

    async def wait_until_done(self, timeout: Optional[float] = None) -> None:
        """Wait until mission completion or timeout."""
        if timeout is not None:
            await asyncio.wait_for(self.done_event.wait(), timeout=timeout)
        else:
            await self.done_event.wait()

    async def handle_event(
        self,
        event: Dict[str, Any] | str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Handle dynamic runtime events (agent_failure, budget_cut, task_added).

        Acquires the engine lock, updates state and queues, and handles cancelled worker cleanup.
        """
        async with self._lock:
            if isinstance(event, str):
                ev_type = event
                ev_payload = dict(event_data or {})
            elif isinstance(event, dict):
                ev_type = str(event.get("type", ""))
                ev_payload = dict(event)
                if "data" in event and isinstance(event["data"], dict):
                    ev_payload.update(event["data"])
            else:
                raise ValidationError(f"Invalid event specification: {event}")

            if not ev_type:
                raise ValidationError("Event type is required")

            if ev_type == "agent_failure":
                await self._handle_agent_failure_locked(ev_payload)
            elif ev_type == "budget_cut":
                await self._handle_budget_cut_locked(ev_payload)
            elif ev_type == "task_added":
                await self._handle_task_added_locked(ev_payload)
            else:
                raise ValidationError(f"Unknown event type: {ev_type}")

    async def _handle_agent_failure_locked(self, event_data: Dict[str, Any]) -> None:
        """
        Handle agent_failure event:
        1. Validate: unknown agent -> NotFound; already dead -> Conflict; no mission running -> Conflict.
        2. Mark agent dead and available=False; cancel ONLY its worker (await it).
        3. If it was running a task: emit task_failed (with wasted partial cost), reset that task to "ready", remove it from running.
        4. Emit agent_failed, increment failures_recovered (only if replan succeeds).
        5. Tasks running on OTHER agents keep running untouched.
        6. Run shared replan procedure.
        """
        # 1. Validation
        agent_id = event_data.get("agent_id")
        if not agent_id or agent_id not in self.state.agents:
            raise NotFound(f"Agent '{agent_id}' not found")

        if agent_id in self.state.dead or self.agent_status.get(agent_id) == "dead":
            raise Conflict(f"Agent '{agent_id}' is already dead")

        if self.state.status != "running":
            raise Conflict(f"No mission running (status: {self.state.status})")

        agent = self.state.agents[agent_id]

        # 2. Mark the agent dead and available=False; cancel ONLY its worker (await it)
        self.agent_status[agent_id] = "dead"
        setattr(agent, "status", "dead")
        agent.available = False
        self.state.dead.add(agent_id)

        worker_task = self._worker_tasks.get(agent_id)
        if worker_task and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        # 3. If running a task: emit task_failed (with wasted partial cost), reset task to "ready", remove from running
        interrupted_task_id: Optional[str] = None
        for tid, aid in list(self.state.running.items()):
            if aid == agent_id:
                interrupted_task_id = tid
                del self.state.running[tid]
                break

        if interrupted_task_id is not None:
            task = self.state.tasks[interrupted_task_id]
            task.status = "ready"
            agent.current_task = None
            spent = self._task_spent_work.get(interrupted_task_id, 0.0)
            partial_cost = spent * agent.cost_per_unit
            self.state.wasted_cost += partial_cost
            self._task_spent_work[interrupted_task_id] = 0.0
            self.emit(
                "task_failed",
                task_id=interrupted_task_id,
                agent_id=agent_id,
                wasted_cost=partial_cost,
                partial_cost=partial_cost,
            )

        # 4. Emit agent_failed (failures_recovered incremented only if replan succeeds)
        self.emit("agent_failed", agent_id=agent_id, interrupted_task=interrupted_task_id)

        # 5. Tasks running on other agents keep running untouched.
        # 6. Shared replan procedure
        pending = [
            t
            for tid, t in self.state.tasks.items()
            if tid not in self.state.done and tid not in self.state.running
        ]

        await self._replan_locked(
            event_type="agent_failure",
            event_data=event_data,
            pending_tasks=pending,
            failed_agent_id=agent_id,
        )

    async def _handle_budget_cut_locked(self, event_data: Dict[str, Any]) -> None:
        """
        Handle budget_cut event:
        The reoptimizer disables agents whose cost_per_unit > new_budget (mutates agent.available).
        Running tasks are NOT killed; they finish.
        Then run the shared replan procedure.
        Documented as a 'max cost per unit' cap.
        """
        if self.state.status != "running":
            raise Conflict(f"No mission running (status: {self.state.status})")

        new_budget_raw = event_data.get(
            "new_budget", event_data.get("budget", event_data.get("max_cost_per_unit"))
        )
        if new_budget_raw is None:
            raise ValidationError("Missing 'new_budget' in event data")

        try:
            new_budget = float(new_budget_raw)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid new_budget value: {new_budget_raw}")

        # Documented: max cost per unit cap
        # Any agent whose cost_per_unit exceeds new_budget is disabled for future task scheduling.
        # Running tasks are NOT killed; they finish. Then pending tasks are replanned with affordable agents.
        self._max_budget = new_budget

        pending = [
            t
            for tid, t in self.state.tasks.items()
            if tid not in self.state.done and tid not in self.state.running
        ]

        await self._replan_locked(
            event_type="budget_cut",
            event_data={"new_budget": new_budget},
            pending_tasks=pending,
        )

    async def _handle_task_added_locked(self, event_data: Dict[str, Any]) -> None:
        """
        Handle task_added event:
        1. Validate: duplicate id -> Conflict; unknown dependency ids -> ValidationError; cycle -> ValidationError.
        2. Add task and done-event to state.
        3. Replan pending + the new task.
        """
        if self.state.status != "running":
            raise Conflict(f"No mission running (status: {self.state.status})")

        raw_task = event_data.get("task", event_data)
        if isinstance(raw_task, dict):
            task_dict = dict(raw_task)
            task_dict.pop("type", None)
            if "id" not in task_dict or not task_dict["id"]:
                raise ValidationError("Task dictionary must include an 'id'")
            try:
                new_task = Task.from_dict(task_dict)
            except Exception as ex:
                raise ValidationError(f"Invalid task dictionary: {ex}")
        elif isinstance(raw_task, Task):
            new_task = raw_task
        else:
            raise ValidationError("Task must be a Task object or dictionary")

        # Validate duplicate id -> Conflict
        if new_task.id in self.state.tasks:
            raise Conflict(f"Task with id '{new_task.id}' already exists")

        # Validate unknown dependency ids -> ValidationError
        for dep in (new_task.deps or []):
            if dep not in self.state.tasks:
                raise ValidationError(
                    f"Unknown dependency id '{dep}' for task '{new_task.id}'"
                )

        # Validate cycle (check with graph.DAG.topological_sort) -> ValidationError
        candidate_tasks = list(self.state.tasks.values()) + [new_task]
        dag = DAG(candidate_tasks)
        try:
            dag.topological_sort()
        except CycleError as ex:
            raise ValidationError(
                f"Cycle detected when adding task '{new_task.id}': {ex}"
            )

        # Add the task and its done-event to state
        if not new_task.deps or all(dep in self.state.done for dep in new_task.deps):
            new_task.status = "ready"
        else:
            new_task.status = "blocked"

        self.state.tasks[new_task.id] = new_task
        self._task_done_events[new_task.id] = asyncio.Event()
        self._task_spent_work[new_task.id] = 0.0

        self.emit(
            "task_added",
            task=new_task.to_dict() if hasattr(new_task, "to_dict") else new_task,
        )

        # Invariant (Prompt 5): exclude new task from pending list, filter deps to pending
        pending = [
            t
            for tid, t in self.state.tasks.items()
            if tid not in self.state.done and tid not in self.state.running and tid != new_task.id
        ]

        await self._replan_locked(
            event_type="task_added",
            event_data={"task": new_task},
            pending_tasks=pending,
            new_task=new_task,
        )

    async def _replan_locked(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        pending_tasks: List[Task],
        new_task: Optional[Task] = None,
        failed_agent_id: Optional[str] = None,
    ) -> bool:
        """
        Shared replan procedure:
        - pending = tasks that are not done and not running.
        - Build COPIES of the pending tasks with deps filtered to ids inside pending.
        - Call ReOptimizer.replan(...) with the copies and living available agents.
          (for agent_failure also include the dead agent in the list; reoptimizer removes it by id).
        - If returned schedule has fewer assignments than pending tasks:
          emit mission_failed with reason listing unassignable task ids, cancel all workers, status = failed.
        - Otherwise: clear ALL queues, load new schedule ordered by start_time, wake all workers,
          and emit 'replanned' with new schedule, per-task status map, reassigned task ids, total_cost,
          projected_finish_t = now + makespan_of_remaining_plan, and CPM details computed on pending tasks.
        """
        pending_ids = set(t.id for t in pending_tasks)

        # Build COPIES of pending tasks with deps filtered to ids inside pending
        copies: List[Task] = []
        for t in pending_tasks:
            tc = copy.deepcopy(t)
            tc.deps = [d for d in (tc.deps or []) if d in pending_ids]
            copies.append(tc)

        # For task_added: exclude new task from pending list, filter new_task.deps to IDs inside pending
        new_task_copy: Optional[Task] = None
        replan_event_data = dict(event_data)
        if event_type == "task_added":
            if new_task is None:
                raise ValidationError("new_task is required for task_added replan")
            new_task_copy = copy.deepcopy(new_task)
            new_task_copy.deps = [d for d in (new_task_copy.deps or []) if d in pending_ids]
            replan_event_data = {"task": new_task_copy}

        # Living available agents (for agent_failure also include dead agent in list)
        living_available_agents = [
            a
            for aid, a in self.state.agents.items()
            if aid not in self.state.dead and a.available
        ]

        if event_type == "agent_failure" and failed_agent_id is not None:
            failed_agent = self.state.agents.get(failed_agent_id)
            if failed_agent is not None:
                agents_for_replan = living_available_agents + [failed_agent]
            else:
                agents_for_replan = living_available_agents
        elif event_type == "budget_cut":
            # ReOptimizer._handle_budget_cut disables agents whose cost_per_unit > new_budget
            agents_for_replan = [
                a for aid, a in self.state.agents.items() if aid not in self.state.dead
            ]
        else:
            agents_for_replan = living_available_agents

        new_schedule = self.reoptimizer.replan(
            event_type=event_type,
            event_data=replan_event_data,
            current_tasks=copies,
            current_agents=agents_for_replan,
            current_schedule=self.state.current_schedule or Schedule(),
        )

        expected_task_ids = set(t.id for t in pending_tasks)
        if event_type == "task_added" and new_task_copy is not None:
            expected_task_ids.add(new_task_copy.id)

        assigned_task_ids = {st.task_id for st in new_schedule.assignments}

        # If returned schedule has fewer assignments than pending tasks: fail mission
        if len(new_schedule.assignments) < len(expected_task_ids):
            unassignable_ids = sorted(list(expected_task_ids - assigned_task_ids))
            reason = f"Unassignable tasks: {', '.join(unassignable_ids)}"
            self.state.status = "failed"
            self.state.failed_reason = reason
            for tid in unassignable_ids:
                if tid in self.state.tasks:
                    self.state.tasks[tid].status = "failed"

            self.emit(
                "mission_failed",
                reason=reason,
                unassignable_tasks=unassignable_ids,
                unassignable_task_ids=unassignable_ids,
            )

            workers = list(self._worker_tasks.values())
            for w in workers:
                if not w.done():
                    w.cancel()
            for ev in self._wake_events.values():
                ev.set()
            for w in workers:
                try:
                    await w
                except asyncio.CancelledError:
                    pass

            self.done_event.set()
            return False

        # Replan succeeded
        self.state.current_schedule = new_schedule
        if event_type == "agent_failure":
            self.state.failures_recovered += 1

        # Clear ALL queues
        for q in self._agent_queues.values():
            q.clear()

        # Load new schedule ordered by start_time
        for assignment in sorted(new_schedule.assignments, key=lambda a: a.start_time):
            if (
                assignment.agent_id in self._agent_queues
                and assignment.agent_id not in self.state.dead
            ):
                self._agent_queues[assignment.agent_id].append(assignment.task_id)

        # Update status for pending tasks
        for tid in expected_task_ids:
            task = self.state.tasks.get(tid)
            if task is not None:
                if all(dep in self.state.done for dep in (task.deps or [])):
                    task.status = "ready"
                else:
                    task.status = "blocked"

        # Wake all workers
        for ev in self._wake_events.values():
            ev.set()

        # CPM details computed on the pending tasks
        all_pending_copies = copies + ([new_task_copy] if new_task_copy is not None else [])
        if all_pending_copies:
            cpm = CPM(all_pending_copies)
            cpm_details = cpm.get_details()
        else:
            cpm_details = {}

        now = self.clock.now()
        projected_finish_t = now + new_schedule.makespan
        task_status_map = {tid: t.status for tid, t in self.state.tasks.items()}
        reassigned_ids = [
            a.task_id for a in sorted(new_schedule.assignments, key=lambda a: a.start_time)
        ]

        self.emit(
            "replanned",
            schedule=new_schedule.to_dict() if hasattr(new_schedule, "to_dict") else new_schedule,
            task_status=task_status_map,
            reassigned_task_ids=reassigned_ids,
            total_cost=new_schedule.total_cost,
            projected_finish_t=projected_finish_t,
            cpm_details=cpm_details,
            cpm=cpm_details,
        )
        return True

    async def _worker_loop(self, agent_id: str) -> None:
        """
        Async worker loop for a single agent.

        Picks the first queued task whose dependencies are satisfied in done,
        runs with simulated ticks, marks completion, and wakes peer agents.
        """
        agent = self.state.agents[agent_id]
        wake_event = self._wake_events[agent_id]

        try:
            while True:
                task_to_run: Optional[Task] = None

                async with self._lock:
                    if self.state.status in ("done", "failed") or agent_id in self.state.dead:
                        break

                    queue = self._agent_queues.get(agent_id, [])
                    # Pick FIRST queued task whose dependencies are all in done
                    for tid in list(queue):
                        task = self.state.tasks.get(tid)
                        if task and all(dep in self.state.done for dep in (task.deps or [])):
                            task_to_run = task
                            queue.remove(tid)
                            break

                    if task_to_run is not None:
                        self.state.running[task_to_run.id] = agent_id
                        task_to_run.status = "running"
                        agent.current_task = task_to_run.id
                        self.agent_status[agent_id] = "busy"
                        setattr(agent, "status", "busy")

                        speed = agent.speed if agent.speed > 0 else 1.0
                        duration = task_to_run.est_time / speed
                        est_end_t = self.clock.now() + duration
                        self.emit(
                            "task_started",
                            task_id=task_to_run.id,
                            agent_id=agent_id,
                            duration=duration,
                            est_end_t=est_end_t,
                        )
                    else:
                        # Clear wake event under lock so no peer can set it before we clear it
                        wake_event.clear()

                if task_to_run is None:
                    if self.state.status in ("done", "failed") or agent_id in self.state.dead:
                        break
                    await wake_event.wait()
                    continue

                # Tick-based task execution
                speed = agent.speed if agent.speed > 0 else 1.0
                remaining_work: float = task_to_run.est_time / speed
                spent_work: float = 0.0

                while remaining_work > 0:
                    await asyncio.sleep(self.tick_duration)
                    dt = self.tick_duration
                    work_this_tick = dt * self.clock.multiplier / self.clock.base_delay
                    consumed = min(remaining_work, work_this_tick)
                    remaining_work -= consumed
                    spent_work += consumed
                    self._task_spent_work[task_to_run.id] = spent_work
                    self.state.actual_cost += consumed * agent.cost_per_unit

                # Mark completion under lock
                async with self._lock:
                    self.state.done.add(task_to_run.id)
                    task_to_run.status = "done"
                    if task_to_run.id in self.state.running:
                        del self.state.running[task_to_run.id]

                    agent.current_task = None
                    if self._max_budget is not None and agent.cost_per_unit > self._max_budget:
                        agent.available = False
                    self.agent_status[agent_id] = "idle"
                    setattr(agent, "status", "idle")
                    self.tasks_done[agent_id] += 1
                    setattr(agent, "tasks_done", self.tasks_done[agent_id])

                    if task_to_run.id in self._task_done_events:
                        self._task_done_events[task_to_run.id].set()

                    self.emit("task_done", task_id=task_to_run.id, agent_id=agent_id)

                    if len(self.state.done) == len(self.state.tasks):
                        self.state.status = "done"
                        total_sim_time = self.clock.now()
                        self.emit(
                            "mission_done",
                            total_time=total_sim_time,
                            duration=total_sim_time,
                            actual_cost=self.state.actual_cost,
                            wasted_cost=self.state.wasted_cost,
                            failures_recovered=self.state.failures_recovered,
                        )
                        self.done_event.set()

                    # Set ALL agents' wake events under lock
                    for ev in self._wake_events.values():
                        ev.set()

        except asyncio.CancelledError:
            # Concurrency Invariant: Workers must NEVER acquire engine lock inside CancelledError/finally
            logger.debug("Worker for agent %s cancelled", agent_id)
            raise
