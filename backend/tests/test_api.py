"""
Tests for FastAPI REST and WebSocket endpoints in app.main.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

import app.main as api_main


@pytest.fixture(autouse=True)
def clean_engine_state():
    """Reset engine state before and after each test."""
    if api_main.current_engine is not None:
        try:
            for worker in list(api_main.current_engine._worker_tasks.values()):
                if not worker.done():
                    worker.cancel()
        except Exception:
            pass
    api_main.current_engine = None
    api_main.task_start_times.clear()
    api_main.task_end_times.clear()
    api_main.manager.active_connections.clear()
    yield
    if api_main.current_engine is not None:
        try:
            for worker in list(api_main.current_engine._worker_tasks.values()):
                if not worker.done():
                    worker.cancel()
        except Exception:
            pass
    api_main.current_engine = None
    api_main.task_start_times.clear()
    api_main.task_end_times.clear()
    api_main.manager.active_connections.clear()


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient with an active BlockingPortal lifespan."""
    with TestClient(api_main.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health & Compare Tests
# ---------------------------------------------------------------------------


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_compare_endpoint_no_mission_default_fixture(client: TestClient) -> None:
    resp = client.get("/compare")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fixture"] == "demo_wide"
    assert "greedy" in data
    assert data["greedy"]["makespan"] > 0
    assert len(data["greedy"]["assignments"]) == 12


def test_compare_endpoint_rest_api_fixture(client: TestClient) -> None:
    resp = client.get("/compare?fixture=rest_api")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fixture"] == "rest_api"
    assert len(data["greedy"]["assignments"]) == 8


def test_compare_endpoint_invalid_fixture(client: TestClient) -> None:
    resp = client.get("/compare?fixture=non_existent_fixture")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mission Creation Tests (POST /mission)
# ---------------------------------------------------------------------------


def test_create_mission_rest_api(client: TestClient) -> None:
    resp = client.post("/mission", json={"fixture": "rest_api"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mission_id"].startswith("mission-")
    assert data["mission"] == "Build and validate a secure REST API"
    assert data["source"] == "rest_api"
    assert len(data["tasks"]) == 8
    assert len(data["agents"]) == 3
    assert "schedule" in data
    assert "critical_path" in data
    assert "cpm_details" in data
    assert data["makespan"] > 0
    assert data["total_cost"] > 0


def test_create_mission_demo_wide(client: TestClient) -> None:
    resp = client.post(
        "/mission",
        json={"fixture": "demo_wide", "mission": "Custom SaaS Build"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mission"] == "Custom SaaS Build"
    assert data["source"] == "demo_wide"
    assert len(data["tasks"]) == 12
    # demo_wide uses agents_default.json (5 agents)
    assert len(data["agents"]) == 5
    assert len(data["critical_path"]) > 0


def test_create_mission_use_gemini_returns_200(client: TestClient) -> None:
    resp = client.post(
        "/mission",
        json={"mission": "Create e-commerce site", "use_gemini": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] in ("gemini", "fallback")
    assert len(data["tasks"]) >= 6


def test_create_mission_missing_fixture_422(client: TestClient) -> None:
    resp = client.post("/mission", json={"mission": "No fixture provided"})
    assert resp.status_code == 422


def test_create_mission_invalid_fixture_422(client: TestClient) -> None:
    resp = client.post("/mission", json={"fixture": "invalid_fixture"})
    assert resp.status_code == 422


def test_create_mission_replaces_previous_mission_cleanly(client: TestClient) -> None:
    resp1 = client.post("/mission", json={"fixture": "rest_api"})
    assert resp1.status_code == 200
    mid1 = resp1.json()["mission_id"]

    resp2 = client.post("/mission", json={"fixture": "demo_wide"})
    assert resp2.status_code == 200
    mid2 = resp2.json()["mission_id"]

    assert mid1 != mid2
    assert api_main.current_engine is not None
    assert api_main.current_engine.state.mission_id == mid2


# ---------------------------------------------------------------------------
# Mission Start Tests (POST /mission/start)
# ---------------------------------------------------------------------------


def test_start_mission_404_no_mission(client: TestClient) -> None:
    resp = client.post("/mission/start")
    assert resp.status_code == 404
    assert "No mission found" in resp.json()["detail"]


def test_start_mission_200_and_conflict_409(client: TestClient) -> None:
    os.environ["SWARM_TICK_DURATION"] = "0.01"
    os.environ["SWARM_BASE_DELAY"] = "0.05"
    client.post("/mission", json={"fixture": "rest_api"})
    resp = client.post("/mission/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    # Second start while running yields 409
    resp_conflict = client.post("/mission/start")
    assert resp_conflict.status_code == 409
    assert "already running" in resp_conflict.json()["detail"]


# ---------------------------------------------------------------------------
# State Snapshot Tests (GET /state)
# ---------------------------------------------------------------------------


def test_get_state_idle_no_mission(client: TestClient) -> None:
    resp = client.get("/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "snapshot"
    assert data["status"] == "idle"
    assert data["mission"] is None
    assert data["agents"] == []
    assert data["tasks"] == []


def test_get_state_with_mission(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    resp = client.get("/state")
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["type"] == "snapshot"
    assert snap["status"] == "idle"
    assert snap["mission"] == "Build and validate a secure REST API"
    assert len(snap["agents"]) == 3
    assert len(snap["tasks"]) == 8
    assert "current_schedule" in snap
    assert "critical_path" in snap
    assert "cpm_details" in snap
    assert "events" in snap

    # Validate agent structure
    agent0 = snap["agents"][0]
    for key in [
        "id",
        "name",
        "skills",
        "speed",
        "cost_per_unit",
        "status",
        "current_task",
        "tasks_done",
    ]:
        assert key in agent0

    # Validate task structure
    task0 = snap["tasks"][0]
    for key in [
        "id",
        "name",
        "required_skill",
        "deps",
        "priority",
        "status",
        "agent_id",
        "start_t",
        "end_t",
    ]:
        assert key in task0


# ---------------------------------------------------------------------------
# Speed Tests (POST /speed)
# ---------------------------------------------------------------------------


def test_speed_404_no_mission(client: TestClient) -> None:
    resp = client.post("/speed", json={"multiplier": 2.0})
    assert resp.status_code == 404


def test_speed_valid_and_bounds_validation(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})

    # Valid
    resp = client.post("/speed", json={"multiplier": 2.5})
    assert resp.status_code == 200
    assert resp.json()["multiplier"] == 2.5

    # Out of bounds low (< 0.25)
    resp_low = client.post("/speed", json={"multiplier": 0.1})
    assert resp_low.status_code == 422

    # Out of bounds high (> 4.0)
    resp_high = client.post("/speed", json={"multiplier": 5.0})
    assert resp_high.status_code == 422


# ---------------------------------------------------------------------------
# Report Tests (GET /report)
# ---------------------------------------------------------------------------


def test_report_404_no_mission(client: TestClient) -> None:
    resp = client.get("/report")
    assert resp.status_code == 404


def test_report_200_with_mission(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    resp = client.get("/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "mission_id" in data
    assert data["mission"] == "Build and validate a secure REST API"
    assert data["status"] == "idle"
    assert "total_time" in data
    assert "actual_cost" in data
    assert "wasted_cost" in data
    assert "failures_recovered" in data
    assert data["tasks_total"] == 8
    assert data["tasks_done"] == 0


# ---------------------------------------------------------------------------
# Event Endpoint Tests (POST /event)
# ---------------------------------------------------------------------------


def test_event_404_no_mission(client: TestClient) -> None:
    resp = client.post("/event", json={"type": "agent_failure", "agent_id": "a1"})
    assert resp.status_code == 404


def test_event_invalid_type_422(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    resp = client.post("/event", json={"type": "invalid_event_type"})
    assert resp.status_code == 422


def test_event_agent_failure_unknown_agent_404(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    client.post("/mission/start")
    resp = client.post("/event", json={"type": "agent_failure", "agent_id": "ghost_agent"})
    assert resp.status_code == 404


def test_event_agent_failure_not_running_409(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    # Status is idle, not running
    resp = client.post("/event", json={"type": "agent_failure", "agent_id": "a1"})
    assert resp.status_code == 409


def test_event_agent_failure_already_dead_409(client: TestClient) -> None:
    os.environ["SWARM_TICK_DURATION"] = "0.01"
    os.environ["SWARM_BASE_DELAY"] = "0.05"
    client.post("/mission", json={"fixture": "rest_api"})
    client.post("/mission/start")

    # First kill -> 200
    resp1 = client.post("/event", json={"type": "agent_failure", "agent_id": "a2"})
    assert resp1.status_code == 200

    # Second kill on same agent -> 409
    resp2 = client.post("/event", json={"type": "agent_failure", "agent_id": "a2"})
    assert resp2.status_code == 409


def test_event_budget_cut_validation(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    # Not running -> 409
    resp = client.post("/event", json={"type": "budget_cut", "new_budget": 2.5})
    assert resp.status_code == 409

    client.post("/mission/start")
    # Missing new_budget -> 422
    resp_missing = client.post("/event", json={"type": "budget_cut"})
    assert resp_missing.status_code == 422

    # Valid budget cut -> 200
    resp_valid = client.post("/event", json={"type": "budget_cut", "new_budget": 2.5})
    assert resp_valid.status_code == 200


def test_event_task_added_validation(client: TestClient) -> None:
    client.post("/mission", json={"fixture": "rest_api"})
    client.post("/mission/start")

    # Duplicate ID -> 409
    resp_dup = client.post(
        "/event",
        json={
            "type": "task_added",
            "task": {
                "id": "t1",
                "name": "Duplicate T1",
                "required_skill": "backend",
                "est_time": 2,
                "est_cost": 4,
                "priority": "low",
                "deps": [],
                "status": "ready",
            },
        },
    )
    assert resp_dup.status_code == 409

    # Unknown dependency -> 422
    resp_unknown = client.post(
        "/event",
        json={
            "type": "task_added",
            "task": {
                "id": "t99",
                "name": "T99",
                "required_skill": "backend",
                "est_time": 2,
                "est_cost": 4,
                "priority": "low",
                "deps": ["ghost_task"],
                "status": "blocked",
            },
        },
    )
    assert resp_unknown.status_code == 422

    # Valid task added -> 200
    resp_valid = client.post(
        "/event",
        json={
            "type": "task_added",
            "task": {
                "id": "t99",
                "name": "Audit Logs",
                "required_skill": "backend",
                "est_time": 2,
                "est_cost": 4,
                "priority": "low",
                "deps": ["t1"],
                "status": "blocked",
            },
        },
    )
    assert resp_valid.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket Tests (/ws)
# ---------------------------------------------------------------------------


def test_websocket_snapshot_and_events_in_order(client: TestClient) -> None:
    """
    Connect to /ws, immediately receive snapshot,
    then start mission and receive task_started / task_done in order.
    """
    os.environ["SWARM_TICK_DURATION"] = "0.01"
    os.environ["SWARM_BASE_DELAY"] = "0.05"

    client.post("/mission", json={"fixture": "rest_api"})

    with client.websocket_connect("/ws") as ws:
        # First message on connect is snapshot
        first_msg = ws.receive_json()
        assert first_msg["type"] == "snapshot"
        assert first_msg["mission"] == "Build and validate a secure REST API"
        assert "t" in first_msg
        assert "seq" in first_msg
        assert len(first_msg["tasks"]) == 8
        assert len(first_msg["agents"]) == 3

        # Start the mission
        start_resp = client.post("/mission/start")
        assert start_resp.status_code == 200

        # Receive stream of events
        received_event_types: List[str] = []
        for _ in range(10):
            msg = ws.receive_json()
            received_event_types.append(msg["type"])
            assert "t" in msg
            assert "seq" in msg
            if "task_done" in received_event_types:
                break

        assert "mission_started" in received_event_types
        assert "task_started" in received_event_types
        assert "task_done" in received_event_types

        # Verify task_started precedes task_done
        started_idx = received_event_types.index("task_started")
        done_idx = received_event_types.index("task_done")
        assert started_idx < done_idx


def test_websocket_silently_drops_dead_sockets(client: TestClient) -> None:
    """Verify dead sockets are cleaned up without crashing the engine."""
    with client.websocket_connect("/ws") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert len(api_main.manager.active_connections) == 1

    # Context closed: client disconnected
    # Broadcasting should not fail and drops disconnected socket
    client.portal.call(api_main.manager.broadcast, {"type": "test", "t": 0.0, "seq": 99})
    assert len(api_main.manager.active_connections) == 0
