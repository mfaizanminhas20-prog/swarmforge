<div align="center">
  
# 🚀 SWARMFORGE
### A Dynamic Multi-Agent Task Allocation, Scheduling & Failure-Recovery System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20React%20Flow-61DAFB.svg)](https://reactjs.org/)
[![Status](https://img.shields.io/badge/Status-In%20Development-orange.svg)]()
[![Course](https://img.shields.io/badge/Course-Design%20and%20Analysis%20of%20Algorithms-green.svg)]()

*SWARMFORGE is a domain-agnostic mission orchestrator. It breaks complex missions (like "Build a REST API" or "Plan a Wedding") into smaller tasks, builds a dependency graph (DAG), assigns tasks to the best-suited AI agents, and dynamically re-plans live if an agent fails or constraints change.*

</div>

---

## 🧠 Core Idea
Convert a complex objective into a dependency graph, assign tasks to suitable AI agents, execute independent work in parallel, and **dynamically rebuild the plan** when an agent fails or constraints change. 

> **Domain-Agnostic:** The system doesn't care what the mission is. It only understands tasks, dependencies, and agents. We use the **Gemini API** to dynamically decompose real-world missions into structured JSON tasks.

## ✨ Key Features
- **Mission Decomposition:** Uses Gemini API to convert user goals into a structured Task List.
- **DAG Manager:** Uses Topological Sort to ensure tasks run in the correct order.
- **Critical Path Method (CPM):** Identifies tasks that drive the total mission completion time.
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
│   │   ├── algorithms/       # DAG, CPM, Scheduler, Reoptimizer (Completed)
│   │   ├── api/              # FastAPI endpoints
│   │   ├── events/           # Event Bus & Simulator
│   │   └── executor/         # Agent Executor
│   ├── fixtures/             # Test data (e.g., REST API mission)
│   └── tests/                # Unit tests for algorithms
├── frontend/                 # React Dashboard (React Flow + Recharts)
└── docs/                     # Report & Demo Scripts
