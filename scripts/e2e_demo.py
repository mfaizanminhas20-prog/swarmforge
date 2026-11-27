#!/usr/bin/env python3
"""
End-to-End Demonstration and Resilience Benchmark Script (Prompt 9).

Performs:
1. POST /mission with fixture demo_wide
2. Connect to /ws and receive initial snapshot
3. POST /mission/start
4. Kill a random agent after exactly 3 task_done events
5. Assert a `replanned` event arrives and `mission_done` follows
6. Print a formatted, readable timeline
7. Repeat for 10 iterations across different agent victims
8. Report final pass rate and metrics
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional
import httpx
import websockets

logger = logging.getLogger("e2e_demo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_WS_URL = "ws://127.0.0.1:8000/ws"
AGENTS_POOL = ["a1", "a2", "a3", "a4", "a5"]


def format_timeline_event(ev: Dict[str, Any]) -> str:
    """Format a single engine event into a concise, readable timeline entry."""
    seq = ev.get("seq", 0)
    t = ev.get("t", 0.0)
    ev_type = ev.get("type", "unknown")
    t_str = f"[{t:6.2f}s]"

    if ev_type == "plan_created":
        makespan = ev.get("makespan", 0.0)
        cost = ev.get("total_cost", 0.0)
        return f"{t_str} SEQ {seq:3d} | PLAN_CREATED    | Initial plan makespan: {makespan:.2f}s, cost: ${cost:.2f}"
    elif ev_type == "mission_started":
        mid = ev.get("mission_id", "")
        return f"{t_str} SEQ {seq:3d} | MISSION_STARTED | Mission '{mid}' started execution"
    elif ev_type == "task_started":
        tid = ev.get("task_id", "")
        aid = ev.get("agent_id", "")
        dur = ev.get("duration", 0.0)
        return f"{t_str} SEQ {seq:3d} | TASK_STARTED    | Task {tid:<3s} -> Agent {aid} (est duration: {dur:.2f}s)"
    elif ev_type == "task_done":
        tid = ev.get("task_id", "")
        aid = ev.get("agent_id", "")
        return f"{t_str} SEQ {seq:3d} | TASK_DONE       | Task {tid:<3s} COMPLETED by Agent {aid}"
    elif ev_type == "task_failed":
        tid = ev.get("task_id", "")
        aid = ev.get("agent_id", "")
        wasted = ev.get("wasted_cost", 0.0)
        return f"{t_str} SEQ {seq:3d} | TASK_FAILED     | Task {tid:<3s} failed on Agent {aid} (wasted: ${wasted:.2f})"
    elif ev_type == "agent_failed":
        aid = ev.get("agent_id", "")
        interrupted = ev.get("interrupted_task")
        int_str = f", interrupted: {interrupted}" if interrupted else ""
        return f"{t_str} SEQ {seq:3d} | AGENT_FAILED    | >>> AGENT {aid} DIED{int_str} <<<"
    elif ev_type == "replanned":
        reassigned = ev.get("reassigned_task_ids", [])
        proj = ev.get("projected_finish_t", 0.0)
        cost = ev.get("total_cost", 0.0)
        return f"{t_str} SEQ {seq:3d} | REPLANNED       | Replanned {len(reassigned)} tasks, projected finish: {proj:.2f}s, cost: ${cost:.2f}"
    elif ev_type == "mission_done":
        total_t = ev.get("total_time", 0.0)
        actual_c = ev.get("actual_cost", 0.0)
        wasted_c = ev.get("wasted_cost", 0.0)
        rec = ev.get("failures_recovered", 0)
        return f"{t_str} SEQ {seq:3d} | MISSION_DONE    | Finished in {total_t:.2f}s | Cost: ${actual_c:.2f} (wasted: ${wasted_c:.2f}) | Recoveries: {rec}"
    elif ev_type == "mission_failed":
        reason = ev.get("reason", "unknown")
        return f"{t_str} SEQ {seq:3d} | MISSION_FAILED  | FAILED: {reason}"
    else:
        return f"{t_str} SEQ {seq:3d} | {ev_type.upper():<15s} | {json.dumps({k: v for k, v in ev.items() if k not in ('seq', 't', 'type')})}"


async def run_single_e2e_iteration(
    iteration: int,
    victim: str,
    base_url: str,
    ws_url: str,
    timeout: float = 20.0,
) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
    """
    Execute one complete E2E mission run:
    1. POST /mission with fixture demo_wide
    2. Connect to /ws and verify snapshot
    3. POST /mission/start
    4. Kill victim after 3 task_done events
    5. Await completion and verify assertions
    """
    timeline: List[Dict[str, Any]] = []
    error_msg: Optional[str] = None

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http_client:
        # Step 1: POST /mission
        post_mission_resp = await http_client.post(
            "/mission",
            json={"fixture": "demo_wide"},
        )
        if post_mission_resp.status_code != 200:
            return False, timeline, f"POST /mission failed: {post_mission_resp.status_code} - {post_mission_resp.text}"

        mission_data = post_mission_resp.json()
        task_deps_map: Dict[str, List[str]] = {
            t["id"]: list(t.get("deps", [])) for t in mission_data.get("tasks", [])
        }

        # Step 2: Connect to /ws
        try:
            async with websockets.connect(ws_url) as ws:
                # Receive initial snapshot
                raw_snapshot = await asyncio.wait_for(ws.recv(), timeout=5.0)
                snapshot = json.loads(raw_snapshot)
                assert snapshot.get("type") == "snapshot", f"Expected snapshot, got {snapshot.get('type')}"

                # Step 3: POST /mission/start
                start_resp = await http_client.post("/mission/start")
                if start_resp.status_code != 200:
                    return False, timeline, f"POST /mission/start failed: {start_resp.status_code} - {start_resp.text}"

                # Step 4: Stream events, kill victim after exactly 3 task_done events
                task_done_count = 0
                killed = False

                async def event_collector() -> None:
                    nonlocal task_done_count, killed
                    async for raw_ev in ws:
                        ev = json.loads(raw_ev)
                        timeline.append(ev)
                        ev_type = ev.get("type")

                        if ev_type == "task_done":
                            task_done_count += 1
                            if task_done_count == 3 and not killed:
                                killed = True
                                # Kill victim agent
                                kill_resp = await http_client.post(
                                    "/event",
                                    json={"type": "agent_failure", "agent_id": victim},
                                )
                                assert kill_resp.status_code == 200, (
                                    f"Failed to kill agent {victim}: {kill_resp.status_code} - {kill_resp.text}"
                                )

                        if ev_type in ("mission_done", "mission_failed"):
                            break

                await asyncio.wait_for(event_collector(), timeout=timeout)

        except asyncio.TimeoutError:
            return False, timeline, f"Timed out waiting for mission completion after {timeout}s"
        except Exception as ex:
            return False, timeline, f"Exception during execution: {ex}"

    # Step 5: Strict Assertions
    replanned_events = [ev for ev in timeline if ev.get("type") == "replanned"]
    mission_done_events = [ev for ev in timeline if ev.get("type") == "mission_done"]
    agent_failed_events = [ev for ev in timeline if ev.get("type") == "agent_failed"]
    task_done_events = [ev for ev in timeline if ev.get("type") == "task_done"]
    task_started_events = [ev for ev in timeline if ev.get("type") == "task_started"]

    # Assertion A: Replanned event arrives
    if not replanned_events:
        return False, timeline, "No 'replanned' event arrived after agent failure"

    # Assertion B: Mission_done follows
    if not mission_done_events:
        return False, timeline, "No 'mission_done' event followed replanning"

    replanned_seq = replanned_events[0].get("seq", 0)
    done_seq = mission_done_events[0].get("seq", 0)
    if replanned_seq >= done_seq:
        return False, timeline, f"replanned event (seq {replanned_seq}) occurred after mission_done (seq {done_seq})"

    # Assertion C: All 12 tasks completed
    if len(task_done_events) != 12:
        return False, timeline, f"Expected 12 completed tasks, got {len(task_done_events)}"

    # Assertion D: No task completes twice
    done_ids = [ev.get("task_id") for ev in task_done_events]
    if len(done_ids) != len(set(done_ids)):
        return False, timeline, f"Duplicate task completions detected: {done_ids}"

    # Assertion E: Every task starts after its dependencies are done
    dep_finish_seq: Dict[str, int] = {ev.get("task_id"): ev.get("seq", 0) for ev in task_done_events}
    for ev in task_started_events:
        tid = ev.get("task_id", "")
        start_seq = ev.get("seq", 0)
        deps = task_deps_map.get(tid, [])
        for dep in deps:
            if dep not in dep_finish_seq or dep_finish_seq[dep] >= start_seq:
                return False, timeline, (
                    f"Dependency violation: Task {tid} started at seq {start_seq} "
                    f"before dep {dep} finished at seq {dep_finish_seq.get(dep)}"
                )

    # Assertion F: Dead agent never starts or finishes a task after its agent_failed event
    if agent_failed_events:
        failed_seq = agent_failed_events[0].get("seq", 0)
        for ev in timeline:
            if ev.get("seq", 0) > failed_seq:
                if ev.get("type") in ("task_started", "task_done") and ev.get("agent_id") == victim:
                    return False, timeline, (
                        f"Dead agent {victim} executed {ev.get('type')} at seq {ev.get('seq')} "
                        f"after agent_failed at seq {failed_seq}"
                    )

    return True, timeline, None


async def ensure_server_running(base_url: str) -> Optional[subprocess.Popen]:
    """Check if server is responding; if not, spawn uvicorn subprocess and wait for /health."""
    async with httpx.AsyncClient(base_url=base_url, timeout=1.0) as client:
        try:
            resp = await client.get("/health")
            if resp.status_code == 200:
                logger.info("Connected to existing running SWARMFORGE server at %s", base_url)
                return None
        except Exception:
            pass

    logger.info("No server detected at %s. Launching uvicorn background process...", base_url)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(repo_root, "backend")

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["SWARM_BASE_DELAY"] = "0.02"
    env["SWARM_TICK_DURATION"] = "0.01"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for /health
    start_time = time.time()
    while time.time() - start_time < 10.0:
        await asyncio.sleep(0.3)
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=1.0) as client:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    logger.info("Spawned server is ready on %s", base_url)
                    return proc
        except Exception:
            pass

    proc.terminate()
    raise RuntimeError(f"Server at {base_url} failed to start within 10 seconds.")


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="SWARMFORGE E2E Demonstration")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="Base HTTP URL of SWARMFORGE API")
    parser.add_argument("--ws", default=DEFAULT_WS_URL, help="WebSocket URL of SWARMFORGE API")
    parser.add_argument("--runs", type=int, default=10, help="Number of test runs")
    args = parser.parse_args()

    server_proc = await ensure_server_running(args.url)

    try:
        total_runs = args.runs
        passed_runs = 0
        failed_runs = 0
        victim_assignments = [AGENTS_POOL[i % len(AGENTS_POOL)] for i in range(total_runs)]

        print("\n" + "=" * 70)
        print("  SWARMFORGE E2E MULTI-AGENT RECOVERY BENCHMARK")
        print(f"  Target: {args.url} | Iterations: {total_runs}")
        print("=" * 70 + "\n")

        for run_idx in range(total_runs):
            victim = victim_assignments[run_idx]
            print(f"--- Run {run_idx + 1}/{total_runs} (Victim: Agent '{victim}') ---")

            success, timeline, err = await run_single_e2e_iteration(
                iteration=run_idx + 1,
                victim=victim,
                base_url=args.url,
                ws_url=args.ws,
            )

            # Print readable timeline for this run
            print(f"\nTimeline for Run {run_idx + 1} ({len(timeline)} events):")
            for ev in timeline:
                print("  " + format_timeline_event(ev))
            print()

            if success:
                passed_runs += 1
                print(f"[PASS] Run {run_idx + 1}: replanned received, mission_done verified.\n")
            else:
                failed_runs += 1
                print(f"[FAIL] Run {run_idx + 1}: {err}\n")

        # Summary
        pass_rate = (passed_runs / total_runs) * 100.0
        print("=" * 70)
        print("  BENCHMARK SUMMARY")
        print(f"  Total Runs:  {total_runs}")
        print(f"  Passed:      {passed_runs}")
        print(f"  Failed:      {failed_runs}")
        print(f"  Pass Rate:   {pass_rate:.1f}%")
        print(f"  Victims:     {victim_assignments}")
        print("=" * 70 + "\n")

        return 0 if failed_runs == 0 else 1

    finally:
        if server_proc is not None:
            logger.info("Stopping spawned background server process...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3.0)
            except Exception:
                server_proc.kill()


def main() -> None:
    code = asyncio.run(main_async())
    sys.exit(code)


if __name__ == "__main__":
    main()
