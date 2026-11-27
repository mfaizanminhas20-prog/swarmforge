"""
SWARMFORGE Gemini LLM Mission Decomposer.

Decomposes a high-level mission into a Directed Acyclic Graph (DAG) of executable
subtasks using Google Gemini via the google-genai SDK with structured JSON output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, List, Literal, Optional, Sequence, Set, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import types
import jsonschema
from pydantic import BaseModel, Field

from app.algorithms.graph import DAG, CycleError
from app.algorithms.models import Agent, Task

# Load environment configuration
load_dotenv()

logger = logging.getLogger("swarmforge.decomposer")


class DecomposerValidationError(Exception):
    """Raised when decomposed tasks fail validation constraints."""
    pass


class TaskItem(BaseModel):
    """Pydantic model representing structured task generation schema."""
    id: str = Field(description="Task identifier strictly in the form t1, t2, ..., tn")
    name: str = Field(description="Descriptive name of the task")
    required_skill: str = Field(description="Required skill chosen strictly from the vocabulary")
    est_time: float = Field(description="Estimated execution time in simulated units, between 1 and 10")
    est_cost: float = Field(description="Estimated task cost in dollars, positive number")
    priority: Literal["low", "medium", "high"] = Field(description="Task execution priority")
    deps: List[str] = Field(default_factory=list, description="IDs of prerequisite tasks referencing earlier task IDs only")
    status: Literal["blocked"] = Field(default="blocked", description="Initial task status, must be 'blocked'")


def load_task_schema() -> dict[str, Any]:
    """Load JSON schema from schemas/task.schema.json."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "schemas" / "task.schema.json",
        Path("schemas/task.schema.json"),
        Path("../schemas/task.schema.json"),
    ]
    for p in candidates:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("Could not find schemas/task.schema.json")


def load_fallback_tasks() -> List[Task]:
    """Load tasks from fixtures/demo_wide.json as safe fallback."""
    candidates = [
        Path(__file__).resolve().parent.parent / "fixtures" / "demo_wide.json",
        Path("backend/fixtures/demo_wide.json"),
        Path("fixtures/demo_wide.json"),
    ]
    for p in candidates:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Task.from_dict(t) for t in data["tasks"]]
    raise FileNotFoundError("Could not find fixtures/demo_wide.json")


def extract_skill_vocabulary(agents: Any) -> List[str]:
    """Extract sorted list of unique skills from agents collection."""
    vocabulary: Set[str] = set()
    if isinstance(agents, dict):
        agents_iter: Iterable[Any] = agents.values()
    elif isinstance(agents, (list, tuple, set)):
        agents_iter = agents
    else:
        agents_iter = [agents]

    for agent in agents_iter:
        if hasattr(agent, "skills") and isinstance(agent.skills, (list, tuple, set)):
            vocabulary.update(agent.skills)
        elif isinstance(agent, dict) and "skills" in agent and isinstance(agent["skills"], (list, tuple, set)):
            vocabulary.update(agent["skills"])

    return sorted(list(vocabulary))


def validate_tasks(
    raw_tasks: Any,
    task_schema: dict[str, Any],
    skill_vocabulary: Sequence[str],
) -> List[Task]:
    """
    Validate decomposed tasks against all system requirements:
    - Must be a list
    - 6 to 14 tasks
    - Sequential unique IDs from t1 to tn
    - jsonschema validation against schemas/task.schema.json
    - required_skill in vocabulary
    - status == 'blocked'
    - est_time between 1 and 10
    - est_cost > 0
    - deps exist and reference earlier ids only
    - DAG cycle check with DAG.topological_sort()
    """
    if not isinstance(raw_tasks, list):
        raise DecomposerValidationError(f"Output must be a JSON array of tasks, got {type(raw_tasks).__name__}")

    n = len(raw_tasks)
    if not (6 <= n <= 14):
        raise DecomposerValidationError(f"Expected between 6 and 14 tasks, got {n}")

    expected_ids = [f"t{i}" for i in range(1, n + 1)]
    actual_ids: List[str] = []

    for idx, t_data in enumerate(raw_tasks):
        if not isinstance(t_data, dict):
            raise DecomposerValidationError(f"Task at index {idx} must be an object, got {type(t_data).__name__}")
        tid = t_data.get("id")
        if not isinstance(tid, str):
            raise DecomposerValidationError(f"Task at index {idx} has invalid id: {tid}")
        actual_ids.append(tid)

    if len(set(actual_ids)) != len(actual_ids):
        raise DecomposerValidationError(f"Task IDs must be unique, got duplicate IDs: {actual_ids}")

    if actual_ids != expected_ids:
        raise DecomposerValidationError(f"Task IDs must be strictly sequential t1..t{n}, got {actual_ids}")

    id_set = set(actual_ids)
    task_objs: List[Task] = []
    vocab_set = set(skill_vocabulary)

    for idx, t_data in enumerate(raw_tasks):
        # jsonschema validation
        try:
            jsonschema.validate(instance=t_data, schema=task_schema)
        except jsonschema.ValidationError as err:
            raise DecomposerValidationError(f"Task {t_data.get('id', idx)} failed schema validation: {err.message}")

        tid = t_data["id"]
        skill = t_data["required_skill"]
        if skill not in vocab_set:
            raise DecomposerValidationError(
                f"Task {tid} has unknown required_skill '{skill}'. Allowed vocabulary: {sorted(list(vocab_set))}"
            )

        status = t_data.get("status")
        if status != "blocked":
            raise DecomposerValidationError(f"Task {tid} status must be 'blocked', got '{status}'")

        try:
            est_time = float(t_data.get("est_time", 0))
        except (ValueError, TypeError):
            raise DecomposerValidationError(f"Task {tid} est_time is not a valid number")

        if not (1.0 <= est_time <= 10.0):
            raise DecomposerValidationError(f"Task {tid} est_time must be between 1 and 10, got {est_time}")

        try:
            est_cost = float(t_data.get("est_cost", 0))
        except (ValueError, TypeError):
            raise DecomposerValidationError(f"Task {tid} est_cost is not a valid number")

        if est_cost <= 0:
            raise DecomposerValidationError(f"Task {tid} est_cost must be > 0, got {est_cost}")

        deps = t_data.get("deps", [])
        earlier_ids = set(actual_ids[:idx])
        for dep in deps:
            if dep not in id_set:
                raise DecomposerValidationError(f"Task {tid} references nonexistent dependency '{dep}'")
            if dep not in earlier_ids:
                raise DecomposerValidationError(
                    f"Task {tid} dependency '{dep}' must reference an earlier task ID (allowed: {sorted(list(earlier_ids))})"
                )

        task_objs.append(Task.from_dict(t_data))

    # DAG cycle check
    dag = DAG(task_objs)
    try:
        dag.topological_sort()
    except CycleError as err:
        raise DecomposerValidationError(f"DAG cycle detected: {err}")
    except Exception as err:
        raise DecomposerValidationError(f"DAG validation failed: {err}")

    return task_objs


def _call_gemini_sync(
    client: Any,
    model: str,
    prompt: str,
    system_instruction: str,
) -> str:
    """Synchronous worker to call Gemini API via client.models.generate_content."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=List[TaskItem],
        temperature=0.2,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    if not response or not hasattr(response, "text") or not response.text:
        raise RuntimeError("Empty response received from Gemini model")
    return response.text


async def decompose(
    mission: str,
    agents: Any,
    client: Optional[Any] = None,
) -> Tuple[List[Task], str]:
    """
    Decompose a mission into a DAG of tasks using Google Gemini.

    Returns:
        (tasks, source) where source is 'gemini' on success or 'fallback' on failure.
        Never raises to the API caller.
    """
    skill_vocabulary = extract_skill_vocabulary(agents)
    if not skill_vocabulary:
        logger.warning("No agent skills found in agents collection; using fallback")
        return load_fallback_tasks(), "fallback"

    try:
        task_schema = load_task_schema()
    except Exception as e:
        logger.error("Failed to load task schema: %s; using fallback", e)
        return load_fallback_tasks(), "fallback"

    model_name = os.environ.get("GEMINI_MODEL")
    if not model_name:
        logger.warning("GEMINI_MODEL environment variable not set, defaulting to 'gemini-3.8-flash'")
        model_name = "gemini-3.8-flash"

    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in environment; using demo_wide fallback")
            return load_fallback_tasks(), "fallback"
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.error("Failed to initialize Gemini client: %s; using demo_wide fallback", e)
            return load_fallback_tasks(), "fallback"

    system_instruction = (
        "You are an expert project planner and task decomposer for multi-agent execution systems.\n"
        "Given a high-level mission, decompose it into a directed acyclic graph (DAG) of executable subtasks.\n\n"
        "Strict rules and constraints:\n"
        f"1. Allowed skill vocabulary: {', '.join(skill_vocabulary)}.\n"
        "   Every task's required_skill MUST be chosen ONLY from this vocabulary.\n"
        "2. Produce between 6 and 14 tasks in total.\n"
        "3. Task IDs must be strictly sequential starting from t1 to tn (e.g. t1, t2, ..., tn).\n"
        "4. Each task's dependencies (deps) must ONLY reference earlier task IDs. No forward references, self-references, or cycles.\n"
        "5. Task durations (est_time) must be numbers between 1 and 10 (simulated time units).\n"
        "6. Task costs (est_cost) must be positive numbers.\n"
        "7. Priority must be one of: 'low', 'medium', 'high'.\n"
        "8. Status must be 'blocked' for all tasks.\n"
        "9. Forbid any text outside the JSON. Output strictly JSON adhering to the response schema."
    )

    prompt = f"Decompose the following mission into executable tasks:\nMission: {mission}"

    for attempt in range(2):
        try:
            raw_text = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini_sync, client, model_name, prompt, system_instruction),
                timeout=15.0,
            )
        except asyncio.TimeoutError as e:
            logger.error("Gemini call timed out after 15s on attempt %d: %s; using fallback", attempt + 1, e)
            return load_fallback_tasks(), "fallback"
        except Exception as e:
            logger.error("Gemini API/network error on attempt %d: %s; using fallback", attempt + 1, e)
            return load_fallback_tasks(), "fallback"

        # Attempt to parse and validate
        try:
            clean_text = raw_text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_text = "\n".join(lines).strip()

            parsed = json.loads(clean_text)
            if isinstance(parsed, dict) and "tasks" in parsed and isinstance(parsed["tasks"], list):
                parsed = parsed["tasks"]

            validated_tasks = validate_tasks(parsed, task_schema, skill_vocabulary)
            logger.info("Successfully decomposed mission into %d tasks via Gemini", len(validated_tasks))
            return validated_tasks, "gemini"

        except Exception as e:
            logger.warning("Gemini output validation failed on attempt %d: %s", attempt + 1, e)
            if attempt == 0:
                prompt = (
                    f"{prompt}\n\n"
                    f"Previous output failed validation with error:\n{e}\n"
                    "Please fix the error and output strictly valid JSON conforming to all schema and DAG constraints."
                )
            else:
                logger.error("Gemini output failed validation after retry: %s; using fallback", e)
                return load_fallback_tasks(), "fallback"

    return load_fallback_tasks(), "fallback"
