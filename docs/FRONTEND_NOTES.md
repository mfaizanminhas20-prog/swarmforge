# SWARMFORGE Frontend Integration Guide

**Author**: Antigravity Backend Team  
**Audience**: Hassan (Frontend Lead)  
**Target UI**: React Flow DAG Visualizer, Gantt Timeline, Live Telemetry Dashboard  

---

## 1. Overview & Connection Architecture

The SWARMFORGE backend communicates real-time simulation and recovery telemetry via WebSockets with fallback REST queries:

- **WebSocket URL**: `ws://localhost:8000/ws`
- **REST Base URL**: `http://localhost:8000`
- **Interactive API Docs**: `http://localhost:8000/docs`
- **Specification Reference**: [docs/API.md](API.md)

---

## 2. Event Types & UI Node/Gantt State Transitions

Every message over `/ws` contains `{ "type": string, "seq": number, "t": number, ... }`. Below is the exact behavior the frontend must implement for each event type:

| Event Type | Visual Effect on Task Node | Gantt / Agent / System Effect |
| :--- | :--- | :--- |
| **`snapshot`** | Hydrates full initial DAG graph. | Initial full state delivery on connect/reconnect. Hydrates agent states, Gantt bars, CPM details, and initial event log. |
| **`mission_started`** | Nodes ready to run turn light gray/blue. | Mission status changes from `idle` to `running`. Running timer starts. |
| **`task_started`** | **Yellow Node**: Fill or border turns bright yellow (`#EAB308`). Node renders active progress bar. | Agent card changes status from `idle` to `busy`, displaying the active task. Progress bar animates using `duration` and `est_end_t`. |
| **`task_done`** | **Green Node**: Node background turns emerald green (`#22C55E`). Progress bar locks to 100%. | Agent status reverts to `idle`. Completed task counter increments. |
| **`task_failed`** | **Red -> Gray Node**: Flashes **Red** (`#EF4444`) immediately with wasted cost badge, then transitions back to **Gray** (`#9CA3AF`, ready/blocked) when re-queued. | Agent card shows warning. `wasted_cost` is added to the budget accumulator. |
| **`agent_failed`** | None directly on nodes (handled by `task_failed` / `replanned`). | Agent card marked **Dead / Failed** (red skull icon or disabled red border). Excluded from selection dropdowns. |
| **`replanned`** | **Re-layout DAG & Nodes**: Updates pending node statuses (`task_status`: `"ready"` vs `"blocked"`). | **Re-render Gantt chart** using `event.schedule`. Recalculate critical path highlight using `event.cpm_details`. Update projected finish timestamp (`projected_finish_t`) and estimated total cost. |
| **`mission_done`** | All nodes confirmed green. | Displays **Mission Accomplished Modal** showing: `total_time`, `actual_cost`, `wasted_cost`, and `failures_recovered`. Perturbation buttons disabled. |
| **`mission_failed`** | Failed / unassignable tasks highlighted in red. | **Displays `failed_reason` Banner/Panel** prominently at top of screen (e.g., `"Unassignable tasks: t7, t8 due to missing required skill: testing"`). Stops active clocks. |
| **`task_added`** | Dynamically spawns new node in React Flow DAG connected to its dependencies. | Initial status set to `"ready"` or `"blocked"`. Precedes an immediate `replanned` event. |
| **`speed_changed`** | Clock icon updates. | Speed multiplier slider/badge updates to reflect `multiplier` (0.25x – 4.0x). |

### Task Progress Bar Calculation
During `task_started`:
```typescript
// Progress percentage between [0, 100]
const progressPct = Math.min(
  100,
  Math.max(0, ((currentSimTime - start_t) / duration) * 100)
);
```
Where `currentSimTime` is tracked via simulation time `t` from the latest event.

---

## 3. Reconnection & Deduplication Protocol

WebSockets can drop or reconnect during network fluctuations or component remounts:

1. **Snapshot Delivery**:
   Whenever a client connects to `/ws`, the server **immediately** responds with a complete state `snapshot`:
   ```json
   {
     "type": "snapshot",
     "mission": "Build and launch a SaaS MVP",
     "status": "running",
     "t": 12.5,
     "seq": 45,
     "last_seq": 45,
     "agents": [...],
     "tasks": [...],
     "current_schedule": {...},
     "critical_path": ["t1", "t4", "t10", "t11", "t12"],
     "cpm_details": {...},
     "events": [...]
   }
   ```
2. **Sequence Deduplication (`seq`)**:
   - Maintain a local state variable `lastSeenSeq = snapshot.seq`.
   - On every incoming WebSocket event:
     ```typescript
     if (event.seq <= lastSeenSeq) {
       // Stale or duplicate event already incorporated into snapshot
       return;
     }
     lastSeenSeq = event.seq;
     applyEventToState(event);
     ```
   - This prevents race conditions where an event was emitted right as the snapshot was being serialized.

---

## 4. Perturbation Controls Specification

The perturbation panel allows users to inject chaos into the running mission.

### Control 1: Budget Cut (Crucial Labeling Requirement)
> [!IMPORTANT]
> **Label Requirement**: The budget cut control **MUST be labelled "Max cost per unit"** (NOT "Total Budget").

- **Concept**: The budget cut enforces an upper cap on agent hourly/unit rates. Any agent whose `cost_per_unit > new_budget` is disabled for future tasks. Active in-flight tasks are permitted to finish to prevent wasted work.
- **UI Element**: Numeric input field with currency adornment (`$ / unit`).
- **Default Value**: `2.50` (step `0.25`, min `0.5`, max `10.0`).
- **Payload (`POST /event`)**:
  ```json
  {
    "type": "budget_cut",
    "new_budget": 2.50
  }
  ```

### Control 2: Kill Agent
- **UI Element**: Dropdown showing living agents (`status != "dead"`), followed by a "Kill Agent" button.
- **Payload (`POST /event`)**:
  ```json
  {
    "type": "agent_failure",
    "agent_id": "a2"
  }
  ```

### Control 3: Add Dynamic Task
- **UI Element**: Modal form containing:
  - Task ID (e.g., `t_audit`)
  - Name (e.g., `Security Audit`)
  - Skill (dropdown of 8 vocabulary skills)
  - Estimated Time (number, 1–10)
  - Estimated Cost (number)
  - Priority (`low`, `medium`, `high`)
  - Dependencies (multi-select of existing task IDs)
- **Payload (`POST /event`)**:
  ```json
  {
    "type": "task_added",
    "task": {
      "id": "t_audit",
      "name": "Security Audit",
      "required_skill": "security",
      "est_time": 3.0,
      "est_cost": 6.0,
      "priority": "high",
      "deps": ["t1"],
      "status": "blocked"
    }
  }
  ```

### Control 4: Speed Multiplier Slider
- **UI Element**: Slider with snap stops: `0.25x`, `0.5x`, `1.0x`, `2.0x`, `4.0x`.
- **Payload (`POST /speed`)**:
  ```json
  {
    "multiplier": 2.0
  }
  ```

---

## 5. Critical Path & Gantt Dynamic Replanning

When a `replanned` event arrives:
1. **Gantt Chart**: Replace existing planned intervals with `event.schedule.assignments`. Each assignment provides `{ task_id, agent_id, start_time, end_time }`.
2. **Critical Path Highlight**: For each task in `event.cpm_details`:
   - If `cpm_details[tid].critical === true`, style the React Flow edge and node with a **glowing amber/red outline** (`#F59E0B`).
   - If `cpm_details[tid].critical === false`, display its float (`cpm_details[tid].float.toFixed(1) + "s float"`) in the tooltip.
