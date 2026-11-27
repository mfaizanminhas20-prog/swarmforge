"""
Live verification script for Google Gemini LLM mission decomposition.
Makes ONE call to Gemini using the key and model from .env for:
"Plan a 3-day wedding event"
and prints the validated tasks or the fallback reason.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

# Ensure backend directory is in python search path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load .env from backend/.env or root .env
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

from app.algorithms.models import Agent  # noqa: E402
from app.decomposer import decompose  # noqa: E402


def load_agents() -> list[Agent]:
    """Load default agent roster from agents_default.json."""
    fixture_path = BACKEND_DIR / "fixtures" / "agents_default.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Agent.from_dict(a) for a in data]


def main() -> None:
    mission = "Plan a 3-day wedding event"
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    print("=" * 70)
    print("SWARMFORGE LIVE GEMINI DECOMPOSER CHECK")
    print("=" * 70)
    print(f"Mission: {mission}")
    print(f"Configured Model: {model}")
    print(f"API Key Present: {'Yes' if api_key else 'No (will trigger fallback)'}")
    print("-" * 70)

    agents = load_agents()
    print(f"Available Agents: {len(agents)}")
    skills = sorted(list({s for a in agents for s in a.skills}))
    print(f"Skill Vocabulary: {', '.join(skills)}")
    print("-" * 70)
    print("Executing decomposition...")

    tasks, source = asyncio.run(decompose(mission, agents))

    print("-" * 70)
    if source == "gemini":
        print(f"[STATUS: SUCCESS] Decomposed via Google Gemini ({source})")
        print(f"Total Validated Tasks: {len(tasks)}\n")
        print(f"{'ID':<6} | {'Skill':<12} | {'Time':<6} | {'Cost':<7} | {'Pri':<7} | {'Deps':<12} | {'Name'}")
        print("-" * 70)
        for t in tasks:
            deps_str = ",".join(t.deps) if t.deps else "-"
            print(f"{t.id:<6} | {t.required_skill:<12} | {t.est_time:<6.1f} | ${t.est_cost:<6.1f} | {t.priority:<7} | {deps_str:<12} | {t.name}")
    else:
        print(f"[STATUS: FALLBACK] Source: {source}")
        print("Fallback Trigger Reason: GEMINI_API_KEY not configured in .env or API error occurred during call.")
        print(f"Total Fallback Tasks (from demo_wide.json): {len(tasks)}")
        print(f"{'ID':<6} | {'Skill':<12} | {'Time':<6} | {'Cost':<7} | {'Pri':<7} | {'Deps':<12} | {'Name'}")
        print("-" * 70)
        for t in tasks[:5]:
            deps_str = ",".join(t.deps) if t.deps else "-"
            print(f"{t.id:<6} | {t.required_skill:<12} | {t.est_time:<6.1f} | ${t.est_cost:<6.1f} | {t.priority:<7} | {deps_str:<12} | {t.name}")
        if len(tasks) > 5:
            print(f"... and {len(tasks) - 5} more fallback tasks.")
    print("=" * 70)


if __name__ == "__main__":
    main()
