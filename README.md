<div align="center">
  
# 🚀 SWARMFORGE
### A Dynamic Multi-Agent Task Allocation, Scheduling & Failure-Recovery System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-In%20Development-orange.svg)]()
[![Course](https://img.shields.io/badge/Course-Design%20and%20Analysis%20of%20Algorithms-green.svg)]()

*SWARMFORGE is an intelligent software platform that manages a team of specialized AI agents. It breaks complex missions into tasks, builds a dependency graph (DAG), assigns tasks to the best agents, and dynamically re-plans if anything fails.*
</div>

---

## 🧠 Core Idea
Convert a complex objective into a dependency graph, assign tasks to suitable AI agents, execute independent work in parallel, and **dynamically rebuild the plan** when an agent fails or constraints change. 

> **Domain-Agnostic:** The system doesn't care if the mission is "Build a REST API", "Plan a Wedding", or "Analyze Sales Data". It only understands tasks, dependencies, and agents.

## ✨ Key Features
- **Mission Decomposition:** Converts user goals into a structured Task List.
- **DAG Manager:** Uses Topological Sort to ensure tasks run in the correct order.
- **Critical Path Method (CPM):** Identifies tasks that drive the total mission time.
- **Greedy Scheduler:** Assigns tasks to the best-fit agents (based on skill, speed, and cost) while maximizing parallel execution.
- **Dynamic Recovery (The Hero Feature):** Re-plans the remaining work live if an agent crashes, a task is delayed, or budget changes.
- **Algorithm Arena:** Compare our optimized approach against a First-Come-First-Serve (FCFS) baseline.

---

## 📁 Repository Structure
```text
swarmforge/
├── schemas/                  # Frozen JSON contracts (Task, Agent, Event)
├── backend/
│   ├── app/
│   │   ├── algorithms/       # Faizan: DAG, CPM, Scheduler, Reoptimizer
│   │   ├── api/              # Talha: FastAPI endpoints
│   │   ├── events/           # Talha: Event Bus & Simulator
│   │   └── executor/         # Talha: Agent Executor
│   ├── fixtures/             # Test data (e.g., REST API mission)
│   └── tests/                # Unit tests for algorithms
├── frontend/                 # Hassan: React Dashboard (React Flow + Recharts)
└── docs/                     # Huzaifa: Report & Demo Scripts
