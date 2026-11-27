# SWARMFORGE Algorithm Arena Integration Guide

**Author**: Antigravity Backend Team  
**Audience**: Huzaifa (Arena Lead)  
**Primary Endpoints**: `GET /compare`, `GET /report`  
**Primary Mission**: `demo_wide`  

---

## 1. Primary Mission for Algorithm Arena: `demo_wide`

> [!IMPORTANT]
> Always configure the Algorithm Arena to run on the **`demo_wide`** fixture (`fixtures/demo_wide.json` with `fixtures/agents_default.json`).

### Why `demo_wide`?
- **Graph Topology**: `demo_wide` models a realistic "Build and Launch a SaaS MVP" mission with 12 tasks:
  - 1 Start task (`t1`: Requirements & scoping)
  - 8 Parallel module tasks (`t2` through `t9`) spanning distinct skill requirements (`research`, `backend`, `database`, `security`, `testing`, `design`, `writing`)
  - 1 Integration task (`t10`) depending on all parallel modules
  - 1 Validation task (`t11`)
  - 1 Launch task (`t12`)
- **Agent Roster**: Uses the standard 5-agent roster (`agents_default.json`) with varied speeds (0.8x – 1.3x) and costs ($1.60 – $4.00/unit).
- **Benchmark Contrast**: Naive First-Come-First-Serve (FCFS) assigns tasks without awareness of agent cost or critical path duration, causing major agent queue bottlenecks. `GreedyScheduler` optimizes load balancing and cost-speed trade-offs:
  - **Greedy**: Makespan = **27.57s**, Total Cost = **$150.10**
  - **FCFS**: Makespan = **34.24s**, Total Cost = **$175.58**
  - **Benchmark Victory**: Greedy delivers **+19.49% faster makespan** and **+14.51% lower cost**!

---

## 2. Algorithm Comparison Endpoint (`GET /compare`)

### Request
```http
GET /compare?fixture=demo_wide
```
*Note: This endpoint is ergonomically designed to work immediately upon server launch, even if no mission has been initialized yet via `POST /mission`.*

### Response Schema & Key Fields
```json
{
  "fixture": "demo_wide",
  "greedy": {
    "makespan": 27.56934731934732,
    "total_cost": 150.1039627039627,
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a4",
        "start_time": 0.0,
        "end_time": 4.0
      },
      ...
    ]
  },
  "fcfs": {
    "makespan": 34.24242424242424,
    "total_cost": 175.5757575757576,
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a1",
        "start_time": 0.0,
        "end_time": 3.6363636363636362
      },
      ...
    ]
  },
  "improvement": {
    "time_pct": 19.49,
    "cost_pct": 14.51
  }
}
```

### UI Presentation Recommendations
1. **Delta Scorecards**:
   - **Time Saved**: Display `improvement.time_pct` prominently with a green badge (e.g. `⚡ +19.49% Faster`).
   - **Cost Saved**: Display `improvement.cost_pct` with a green badge (e.g. `💰 +14.51% Cost Savings`).
2. **Side-by-Side Dual Gantt Charts**:
   - Render `greedy.assignments` on top and `fcfs.assignments` below on a synchronized time axis.
   - Visually illustrate how FCFS creates idle bubbles and critical path stalls that Greedy eliminates.

---

## 3. Post-Mission Audit Report (`GET /report`)

### Request
```http
GET /report
```
*Note: Available after a mission has run or completed. Returns HTTP 404 if no mission exists.*

### Response Schema & Key Fields
```json
{
  "mission_id": "mission-666d92",
  "mission": "Build and launch a SaaS MVP",
  "status": "done",
  "total_time": 47.65,
  "total_cost": 171.85,
  "actual_cost": 171.85,
  "wasted_cost": 22.40,
  "tasks_completed": 12,
  "tasks_done": 12,
  "tasks_total": 12,
  "failures_recovered": 1,
  "failed_reason": null,
  "event_log": [...]
}
```

### Field Reference for Arena Analytics
| Field | Type | Description |
| :--- | :--- | :--- |
| **`status`** | `string` | `"done"`, `"failed"`, or `"running"` |
| **`total_time`** | `float` | Total simulation seconds elapsed to complete all tasks |
| **`actual_cost`** | `float` | Cumulative productive and wasted execution cost |
| **`wasted_cost`** | `float` | Cost expended on tasks that were interrupted by an agent crash |
| **`tasks_completed`** | `int` | Number of tasks successfully finished |
| **`tasks_total`** | `int` | Total number of tasks in the mission |
| **`failures_recovered`**| `int` | Number of dynamic failure re-optimizations successfully handled |
| **`failed_reason`** | `string|null`| Populated with unassignable task details if status is `"failed"` |
| **`event_log`** | `array` | Complete audit trail of every emitted engine event |

### UI Presentation Recommendations
- **Cost Efficiency Meter**: Show a stacked bar with **Productive Cost** (`actual_cost - wasted_cost`) in blue and **Wasted Cost** (`wasted_cost`) in red/amber.
- **Resilience Badge**: Render a "Self-Healing Counter" showcasing `failures_recovered` recoveries executed live.
