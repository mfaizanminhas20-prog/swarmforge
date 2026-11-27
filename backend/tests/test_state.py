"""
Tests for MissionState and SimClock in backend/app/state.py.
"""

import os
import pytest
from app.algorithms.models import Agent, Task
from app.state import MissionState, SimClock


class MockClock:
    """Mock wall time function for deterministic SimClock testing."""

    def __init__(self, start_time: float = 100.0) -> None:
        self.current_time = start_time

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def test_mission_state_defaults() -> None:
    state = MissionState(mission_id="m1", mission="Test Mission")
    assert state.mission_id == "m1"
    assert state.mission == "Test Mission"
    assert state.tasks == {}
    assert state.agents == {}
    assert state.done == set()
    assert state.running == {}
    assert state.dead == set()
    assert state.current_schedule is None
    assert state.status == "idle"
    assert state.failed_reason is None
    assert state.event_log == []
    assert state.actual_cost == 0.0
    assert state.wasted_cost == 0.0
    assert state.failures_recovered == 0

    d = state.to_dict()
    assert d["mission_id"] == "m1"
    assert d["status"] == "idle"
    assert d["done"] == []
    assert d["dead"] == []


def test_mission_state_collection_normalization() -> None:
    task = Task(id="t1", name="Task 1", required_skill="backend", est_time=1.0, est_cost=2.0)
    agent = Agent(id="a1", name="Agent 1", skills=["backend"])

    # Passed as lists and tuples
    state = MissionState(
        mission_id="m2",
        mission="Normalize Mission",
        tasks=[task],  # type: ignore[arg-type]
        agents=[agent],  # type: ignore[arg-type]
        done=["t1"],  # type: ignore[arg-type]
        dead=("a1",),  # type: ignore[arg-type]
    )

    assert state.tasks == {"t1": task}
    assert state.agents == {"a1": agent}
    assert state.done == {"t1"}
    assert state.dead == {"a1"}

    d = state.to_dict()
    assert "t1" in d["tasks"]
    assert "a1" in d["agents"]
    assert d["done"] == ["t1"]
    assert d["dead"] == ["a1"]


def test_sim_clock_base_delay_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default base_delay without env var is 0.5
    monkeypatch.delenv("SWARM_BASE_DELAY", raising=False)
    clock_default = SimClock()
    assert clock_default.base_delay == 0.5

    # With SWARM_BASE_DELAY env set
    monkeypatch.setenv("SWARM_BASE_DELAY", "0.25")
    clock_env = SimClock()
    assert clock_env.base_delay == 0.25

    # Explicit constructor base_delay overrides env
    clock_explicit = SimClock(base_delay=1.0)
    assert clock_explicit.base_delay == 1.0


def test_sim_clock_advancement_formula() -> None:
    mock_wall = MockClock(start_time=0.0)
    # base_delay = 0.5 wall seconds per 1.0 simulated unit
    # multiplier = 1.0
    clock = SimClock(multiplier=1.0, base_delay=0.5, time_fn=mock_wall)

    assert clock.now() == pytest.approx(0.0)

    # Advance 0.5 wall seconds -> should advance 1.0 sim unit
    mock_wall.advance(0.5)
    assert clock.now() == pytest.approx(1.0)

    # Advance another 1.0 wall seconds -> should advance 2.0 sim units (total 3.0)
    mock_wall.advance(1.0)
    assert clock.now() == pytest.approx(3.0)


def test_sim_clock_multiplier_change_mid_run() -> None:
    mock_wall = MockClock(start_time=50.0)
    clock = SimClock(multiplier=1.0, base_delay=0.5, time_fn=mock_wall)

    # Advance wall time by 1.0s -> sim time = 1.0 * 1.0 / 0.5 = 2.0
    mock_wall.advance(1.0)
    assert clock.now() == pytest.approx(2.0)

    # Speed up 2x: multiplier = 2.0
    # Right at the moment of change, sim time must stay 2.0 (no jump)
    clock.set_multiplier(2.0)
    assert clock.multiplier == 2.0
    assert clock.now() == pytest.approx(2.0)

    # Advance wall time by 0.5s with multiplier 2.0:
    # delta_sim = 0.5 * 2.0 / 0.5 = 2.0
    # total sim time = 2.0 + 2.0 = 4.0
    mock_wall.advance(0.5)
    assert clock.now() == pytest.approx(4.0)

    # Slow down to 0.5x: multiplier = 0.5
    clock.multiplier = 0.5
    assert clock.now() == pytest.approx(4.0)

    # Advance wall time by 2.0s with multiplier 0.5:
    # delta_sim = 2.0 * 0.5 / 0.5 = 2.0
    # total sim time = 4.0 + 2.0 = 6.0
    mock_wall.advance(2.0)
    assert clock.now() == pytest.approx(6.0)


def test_sim_clock_pause_and_resume() -> None:
    mock_wall = MockClock(start_time=0.0)
    clock = SimClock(multiplier=1.0, base_delay=0.5, time_fn=mock_wall)

    mock_wall.advance(1.0)  # sim = 2.0
    assert clock.now() == pytest.approx(2.0)

    # Pause: multiplier = 0.0
    clock.set_multiplier(0.0)
    assert clock.now() == pytest.approx(2.0)

    # Wall time elapses while paused
    mock_wall.advance(10.0)
    assert clock.now() == pytest.approx(2.0), "Clock must not advance while multiplier is 0.0"

    # Resume at 1.0x
    clock.set_multiplier(1.0)
    assert clock.now() == pytest.approx(2.0)

    mock_wall.advance(0.5)
    assert clock.now() == pytest.approx(3.0)


def test_sim_clock_reset() -> None:
    mock_wall = MockClock(start_time=10.0)
    clock = SimClock(multiplier=1.0, base_delay=0.5, time_fn=mock_wall)

    mock_wall.advance(2.0)
    assert clock.now() == pytest.approx(4.0)

    # Reset to 0.0
    clock.reset()
    assert clock.now() == pytest.approx(0.0)

    # Reset to custom sim_time
    clock.reset(sim_time=10.0)
    assert clock.now() == pytest.approx(10.0)

    mock_wall.advance(0.5)
    assert clock.now() == pytest.approx(11.0)
