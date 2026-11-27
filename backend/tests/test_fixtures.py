"""
Tests for default fixtures and their invariants:
- backend/fixtures/agents_default.json
- backend/fixtures/demo_wide.json
"""

import json
from pathlib import Path
import pytest
import jsonschema

from app.algorithms.graph import DAG
from app.algorithms.models import Agent, Task

SKILL_VOCABULARY = [
    "planning",
    "research",
    "backend",
    "database",
    "security",
    "testing",
    "design",
    "writing",
]

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = ROOT_DIR / "schemas"
FIXTURES_DIR = ROOT_DIR / "backend" / "fixtures"


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_agents_default_schema_and_invariants() -> None:
    agent_schema = load_json(SCHEMAS_DIR / "agent.schema.json")
    agents_data = load_json(FIXTURES_DIR / "agents_default.json")

    assert isinstance(agents_data, list), "agents_default.json should be a JSON array of agents"
    assert len(agents_data) == 5, f"Expected exactly 5 agents, got {len(agents_data)}"

    agents: list[Agent] = []
    for agent_raw in agents_data:
        # Schema validation
        jsonschema.validate(instance=agent_raw, schema=agent_schema)
        agent = Agent.from_dict(agent_raw)
        agents.append(agent)

        # Speed and cost bounds
        assert 0.8 <= agent.speed <= 1.3, f"Agent {agent.id} speed {agent.speed} outside [0.8, 1.3]"
        assert 1.5 <= agent.cost_per_unit <= 4.0, (
            f"Agent {agent.id} cost_per_unit {agent.cost_per_unit} outside [1.5, 4.0]"
        )

        # Only skills from vocabulary
        for s in agent.skills:
            assert s in SKILL_VOCABULARY, f"Skill '{s}' on agent {agent.id} not in vocabulary"

    # Speeds and costs vary
    speeds = {a.speed for a in agents}
    costs = {a.cost_per_unit for a in agents}
    assert len(speeds) >= 3, "Agent speeds should vary across agents"
    assert len(costs) >= 3, "Agent costs should vary across agents"

    # INVARIANT: every skill is covered by at least 2 agents
    skill_coverage: dict[str, list[str]] = {s: [] for s in SKILL_VOCABULARY}
    for agent in agents:
        for s in agent.skills:
            skill_coverage[s].append(agent.id)

    for skill, agent_ids in skill_coverage.items():
        assert len(agent_ids) >= 2, (
            f"Invariant violation: skill '{skill}' is only covered by {len(agent_ids)} agent(s): {agent_ids}"
        )

    # FAULT-TOLERANCE INVARIANT:
    # No single agent failure can make a mission unschedulable (every skill covered by remaining agents)
    for failed_agent in agents:
        surviving_agents = [a for a in agents if a.id != failed_agent.id]
        surviving_skills = {s for a in surviving_agents for s in a.skills}
        for skill in SKILL_VOCABULARY:
            assert skill in surviving_skills, (
                f"Single failure invariant broken: If {failed_agent.id} fails, skill '{skill}' has no surviving agents!"
            )


def test_demo_wide_fixture() -> None:
    task_schema = load_json(SCHEMAS_DIR / "task.schema.json")
    demo_data = load_json(FIXTURES_DIR / "demo_wide.json")

    assert isinstance(demo_data, dict), "demo_wide.json must be a dict"
    assert demo_data.get("mission") == "Build and launch a SaaS MVP"
    assert "tasks" in demo_data, "demo_wide.json missing 'tasks'"

    tasks_raw = demo_data["tasks"]
    assert len(tasks_raw) == 12, f"Expected 12 tasks, got {len(tasks_raw)}"

    expected_ids = [f"t{i}" for i in range(1, 13)]
    actual_ids = [t["id"] for t in tasks_raw]
    assert actual_ids == expected_ids, f"Task ids must be exactly t1..t12, got {actual_ids}"

    tasks = [Task.from_dict(t) for t in tasks_raw]
    task_map = {t.id: t for t in tasks}

    # Validate against task schema and assert blocked status and skills
    for t_raw in tasks_raw:
        jsonschema.validate(instance=t_raw, schema=task_schema)
        assert t_raw["status"] == "blocked", f"Task {t_raw['id']} status should be 'blocked'"
        assert t_raw["required_skill"] in SKILL_VOCABULARY, (
            f"Task {t_raw['id']} skill '{t_raw['required_skill']}' not in vocabulary"
        )

    # Topology:
    # - t1: start task, deps: []
    assert task_map["t1"].deps == [], "t1 must be a start task with no deps"

    # - 8 parallel module tasks across different skills: t2..t9 (deps: ["t1"])
    module_skills = set()
    for tid in [f"t{i}" for i in range(2, 10)]:
        t = task_map[tid]
        assert t.deps == ["t1"], f"Module task {tid} must depend solely on t1"
        module_skills.add(t.required_skill)
    assert len(module_skills) == 8, (
        f"The 8 parallel module tasks must cover 8 distinct skills, got {len(module_skills)}: {module_skills}"
    )

    # - t10: integration task depending on module tasks
    assert set(task_map["t10"].deps) == {f"t{i}" for i in range(2, 10)}, (
        "t10 must integrate all 8 parallel module tasks"
    )

    # - t11: staging / validation task
    assert "t10" in task_map["t11"].deps

    # - t12: ship task
    assert "t11" in task_map["t12"].deps

    # Verify DAG validity
    dag = DAG(tasks)
    topo_order = dag.topological_sort()
    assert len(topo_order) == 12
    assert topo_order[0] == "t1"
    assert topo_order[-1] == "t12"


def test_demo_wide_scheduling_with_default_agents() -> None:
    from app.algorithms.scheduler import GreedyScheduler

    demo_data = load_json(FIXTURES_DIR / "demo_wide.json")
    tasks = [Task.from_dict(t) for t in demo_data["tasks"]]
    agents = [Agent.from_dict(a) for a in demo_data["agents"]]

    scheduler = GreedyScheduler()
    schedule = scheduler.greedy_schedule(tasks, agents)

    assert len(schedule.assignments) == 12, "All 12 tasks should be scheduled"
    assert schedule.makespan > 0
    assert schedule.total_cost > 0

