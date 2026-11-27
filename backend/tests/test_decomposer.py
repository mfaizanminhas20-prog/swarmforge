"""
Tests for SWARMFORGE Gemini Decomposer (backend/app/decomposer.py).
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, List
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

from app.algorithms.models import Agent, Task
from app.decomposer import (
    DecomposerValidationError,
    decompose,
    extract_skill_vocabulary,
    load_fallback_tasks,
    load_task_schema,
    validate_tasks,
)
from app.main import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def get_default_agents() -> List[Agent]:
    with open(FIXTURES_DIR / "agents_default.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Agent.from_dict(a) for a in data]


VALID_TASKS_DATA = [
    {
        "id": "t1",
        "name": "Architecture Design",
        "required_skill": "planning",
        "est_time": 4.0,
        "est_cost": 10.0,
        "priority": "high",
        "deps": [],
        "status": "blocked",
    },
    {
        "id": "t2",
        "name": "Database Schema Setup",
        "required_skill": "database",
        "est_time": 3.0,
        "est_cost": 8.0,
        "priority": "high",
        "deps": ["t1"],
        "status": "blocked",
    },
    {
        "id": "t3",
        "name": "Backend Core APIs",
        "required_skill": "backend",
        "est_time": 5.0,
        "est_cost": 15.0,
        "priority": "high",
        "deps": ["t2"],
        "status": "blocked",
    },
    {
        "id": "t4",
        "name": "Security Audit & Auth",
        "required_skill": "security",
        "est_time": 4.0,
        "est_cost": 12.0,
        "priority": "medium",
        "deps": ["t3"],
        "status": "blocked",
    },
    {
        "id": "t5",
        "name": "UI/UX Mockups",
        "required_skill": "design",
        "est_time": 3.0,
        "est_cost": 9.0,
        "priority": "medium",
        "deps": ["t1"],
        "status": "blocked",
    },
    {
        "id": "t6",
        "name": "Integration Testing",
        "required_skill": "testing",
        "est_time": 4.0,
        "est_cost": 10.0,
        "priority": "high",
        "deps": ["t3", "t4", "t5"],
        "status": "blocked",
    },
    {
        "id": "t7",
        "name": "Technical Documentation",
        "required_skill": "writing",
        "est_time": 2.0,
        "est_cost": 5.0,
        "priority": "low",
        "deps": ["t6"],
        "status": "blocked",
    },
]


class MockResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class MockModels:
    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.call_history: List[Any] = []

    def generate_content(self, model: str, contents: str, config: Any) -> Any:
        self.call_history.append({"model": model, "contents": contents, "config": config})
        if not self.responses:
            raise RuntimeError("MockModels has no more responses")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


class MockClient:
    def __init__(self, responses: List[Any]) -> None:
        self.models = MockModels(responses)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_extract_skill_vocabulary() -> None:
    agents = get_default_agents()
    vocab = extract_skill_vocabulary(agents)
    assert "planning" in vocab
    assert "backend" in vocab
    assert "database" in vocab
    assert "writing" in vocab
    assert len(vocab) == 8


def test_validate_tasks_valid() -> None:
    schema = load_task_schema()
    agents = get_default_agents()
    vocab = extract_skill_vocabulary(agents)
    tasks = validate_tasks(VALID_TASKS_DATA, schema, vocab)
    assert len(tasks) == 7
    assert tasks[0].id == "t1"
    assert tasks[-1].id == "t7"


def test_validate_tasks_task_count_bounds() -> None:
    schema = load_task_schema()
    agents = get_default_agents()
    vocab = extract_skill_vocabulary(agents)

    # Less than 6 tasks
    with pytest.raises(DecomposerValidationError, match="Expected between 6 and 14 tasks"):
        validate_tasks(VALID_TASKS_DATA[:5], schema, vocab)

    # More than 14 tasks
    too_many = [
        {
            "id": f"t{i}",
            "name": f"Task {i}",
            "required_skill": "planning",
            "est_time": 2.0,
            "est_cost": 5.0,
            "priority": "medium",
            "deps": [f"t{i-1}"] if i > 1 else [],
            "status": "blocked",
        }
        for i in range(1, 16)
    ]
    with pytest.raises(DecomposerValidationError, match="Expected between 6 and 14 tasks"):
        validate_tasks(too_many, schema, vocab)


@pytest.mark.asyncio
async def test_decomposer_valid_output() -> None:
    agents = get_default_agents()
    mock_client = MockClient([MockResponse(json.dumps(VALID_TASKS_DATA))])

    tasks, source = await decompose("Plan a high performance system", agents, client=mock_client)
    assert source == "gemini"
    assert len(tasks) == 7
    assert len(mock_client.models.call_history) == 1
    assert tasks[0].name == "Architecture Design"


@pytest.mark.asyncio
async def test_decomposer_cyclic_output_retries_and_falls_back() -> None:
    agents = get_default_agents()
    cyclic_data = copy.deepcopy(VALID_TASKS_DATA)
    # Introduce cycle: t1 depends on t2, but t2 also depends on t1
    cyclic_data[0]["deps"] = ["t2"]

    # Both attempts return cyclic output
    mock_client = MockClient([
        MockResponse(json.dumps(cyclic_data)),
        MockResponse(json.dumps(cyclic_data)),
    ])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "fallback"
    assert len(mock_client.models.call_history) == 2
    # Check that fallback returns demo_wide tasks
    assert len(tasks) == 12
    # Verify retry prompt included previous validation error
    retry_prompt = mock_client.models.call_history[1]["contents"]
    assert "Previous output failed validation with error" in retry_prompt


@pytest.mark.asyncio
async def test_decomposer_cyclic_output_succeeds_on_retry() -> None:
    agents = get_default_agents()
    cyclic_data = copy.deepcopy(VALID_TASKS_DATA)
    cyclic_data[0]["deps"] = ["t2"]

    # Attempt 1: cyclic, Attempt 2: valid
    mock_client = MockClient([
        MockResponse(json.dumps(cyclic_data)),
        MockResponse(json.dumps(VALID_TASKS_DATA)),
    ])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "gemini"
    assert len(tasks) == 7
    assert len(mock_client.models.call_history) == 2


@pytest.mark.asyncio
async def test_decomposer_unknown_skill_retries_and_falls_back() -> None:
    agents = get_default_agents()
    bad_data = copy.deepcopy(VALID_TASKS_DATA)
    bad_data[1]["required_skill"] = "quantum_cryptography"

    mock_client = MockClient([
        MockResponse(json.dumps(bad_data)),
        MockResponse(json.dumps(bad_data)),
    ])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "fallback"
    assert len(tasks) == 12
    assert len(mock_client.models.call_history) == 2


@pytest.mark.asyncio
async def test_decomposer_missing_dependency_retries_and_falls_back() -> None:
    agents = get_default_agents()
    bad_data = copy.deepcopy(VALID_TASKS_DATA)
    bad_data[3]["deps"] = ["t99"]

    mock_client = MockClient([
        MockResponse(json.dumps(bad_data)),
        MockResponse(json.dumps(bad_data)),
    ])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "fallback"
    assert len(tasks) == 12
    assert len(mock_client.models.call_history) == 2


@pytest.mark.asyncio
async def test_decomposer_malformed_json_retries_and_falls_back() -> None:
    agents = get_default_agents()
    malformed_json = "{ 'tasks': [ incomplete json text..."

    mock_client = MockClient([
        MockResponse(malformed_json),
        MockResponse(malformed_json),
    ])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "fallback"
    assert len(tasks) == 12
    assert len(mock_client.models.call_history) == 2


@pytest.mark.asyncio
async def test_decomposer_timeout_falls_back() -> None:
    agents = get_default_agents()
    mock_client = mock.MagicMock()

    async def raise_timeout(*args: Any, **kwargs: Any) -> Any:
        raise asyncio.TimeoutError("Operation timed out")

    with mock.patch("asyncio.to_thread", side_effect=raise_timeout):
        tasks, source = await decompose("Plan a system", agents, client=mock_client)

    assert source == "fallback"
    assert len(tasks) == 12


@pytest.mark.asyncio
async def test_decomposer_rate_limit_error_falls_back() -> None:
    agents = get_default_agents()
    rate_limit_error = RuntimeError("429 Resource has been exhausted (rate limit)")

    mock_client = MockClient([rate_limit_error])

    tasks, source = await decompose("Plan a system", agents, client=mock_client)
    assert source == "fallback"
    assert len(tasks) == 12
    assert len(mock_client.models.call_history) == 1


# ---------------------------------------------------------------------------
# Integration with POST /mission
# ---------------------------------------------------------------------------


def test_api_mission_use_gemini_with_mocked_success() -> None:
    client = TestClient(app)
    expected_tasks = [Task.from_dict(t) for t in VALID_TASKS_DATA]

    with mock.patch("app.main.decompose", return_value=(expected_tasks, "gemini")) as mock_dec:
        resp = client.post(
            "/mission",
            json={"mission": "Deploy planetary communication array", "use_gemini": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "gemini"
        assert len(data["tasks"]) == 7
        assert data["makespan"] > 0
        assert data["total_cost"] > 0
        mock_dec.assert_called_once()


def test_api_mission_use_gemini_with_mocked_fallback() -> None:
    client = TestClient(app)
    fallback_tasks = load_fallback_tasks()

    with mock.patch("app.main.decompose", return_value=(fallback_tasks, "fallback")) as mock_dec:
        resp = client.post(
            "/mission",
            json={"mission": "Plan event", "use_gemini": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "fallback"
        assert len(data["tasks"]) == 12
        mock_dec.assert_called_once()
