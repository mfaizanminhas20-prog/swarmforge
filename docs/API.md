# SWARMFORGE API Specification

This document provides complete documentation for the SWARMFORGE REST and WebSocket APIs. All example request and response payloads, as well as WebSocket event payloads, are generated directly from live system test runs.

---

## Architecture & Communication Protocols

- **Base URL**: `http://localhost:8000` (or configured host)
- **CORS**: Configured via the `CORS_ORIGINS` environment variable (defaults to `*`).
- **Telemetry Streaming**: Real-time events are streamed over WebSocket at `/ws`.
- **Event Contract**: Every emitted event adheres to `schemas/event.schema.json` with fields `type`, `t` (simulated timestamp), `seq` (monotonic integer sequence), and optional contextual IDs.

---

## REST Endpoints

### 1. Health Check
`GET /health`

Returns service health status.

#### Response (200 OK)
```json
{
  "status": "ok"
}
```

---

### 2. Compare Algorithms
`GET /compare?fixture=demo_wide`

Compares GreedyScheduler metrics against baseline algorithms. Accepts an optional `?fixture=demo_wide` or `?fixture=rest_api` query parameter even when no mission is active yet.

#### Response (200 OK)
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
      {
        "task_id": "t3",
        "agent_id": "a2",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t4",
        "agent_id": "a1",
        "start_time": 4.0,
        "end_time": 11.272727272727273
      },
      {
        "task_id": "t5",
        "agent_id": "a5",
        "start_time": 4.0,
        "end_time": 7.846153846153846
      },
      {
        "task_id": "t6",
        "agent_id": "a5",
        "start_time": 7.846153846153846,
        "end_time": 12.46153846153846
      },
      {
        "task_id": "t2",
        "agent_id": "a4",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 4.0,
        "end_time": 10.25
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 11.272727272727273,
        "end_time": 14.90909090909091
      },
      {
        "task_id": "t9",
        "agent_id": "a4",
        "start_time": 9.0,
        "end_time": 12.0
      },
      {
        "task_id": "t10",
        "agent_id": "a2",
        "start_time": 14.90909090909091,
        "end_time": 20.742424242424242
      },
      {
        "task_id": "t11",
        "agent_id": "a5",
        "start_time": 20.742424242424242,
        "end_time": 23.81934731934732
      },
      {
        "task_id": "t12",
        "agent_id": "a3",
        "start_time": 23.81934731934732,
        "end_time": 27.56934731934732
      }
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
      {
        "task_id": "t2",
        "agent_id": "a1",
        "start_time": 3.6363636363636362,
        "end_time": 8.181818181818182
      },
      {
        "task_id": "t3",
        "agent_id": "a2",
        "start_time": 3.6363636363636362,
        "end_time": 8.636363636363637
      },
      {
        "task_id": "t4",
        "agent_id": "a1",
        "start_time": 8.181818181818182,
        "end_time": 15.454545454545453
      },
      {
        "task_id": "t5",
        "agent_id": "a2",
        "start_time": 8.636363636363637,
        "end_time": 12.803030303030305
      },
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 3.6363636363636362,
        "end_time": 11.136363636363637
      },
      {
        "task_id": "t7",
        "agent_id": "a2",
        "start_time": 12.803030303030305,
        "end_time": 16.969696969696972
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 15.454545454545453,
        "end_time": 19.09090909090909
      },
      {
        "task_id": "t9",
        "agent_id": "a1",
        "start_time": 19.09090909090909,
        "end_time": 21.818181818181817
      },
      {
        "task_id": "t10",
        "agent_id": "a1",
        "start_time": 21.818181818181817,
        "end_time": 28.18181818181818
      },
      {
        "task_id": "t11",
        "agent_id": "a2",
        "start_time": 28.18181818181818,
        "end_time": 31.515151515151512
      },
      {
        "task_id": "t12",
        "agent_id": "a1",
        "start_time": 31.515151515151512,
        "end_time": 34.24242424242424
      }
    ]
  },
  "improvement": {
    "time_pct": 19.49,
    "cost_pct": 14.51
  }
}
```

---

### 3. Create Mission
`POST /mission`

Initializes mission state and computes the initial greedy execution schedule and CPM critical path.
- When `fixture="rest_api"`, agents are loaded directly from `backend/fixtures/rest_api.json`.
- When `fixture="demo_wide"`, agents are loaded from `backend/fixtures/agents_default.json`.
- A new `POST /mission` cleanly cancels any previous mission's workers.
- When `use_gemini=true`, dynamically decomposes the natural language `mission` prompt into structured tasks using Gemini 3.8 Flash (`source="gemini"`), or falls back to `demo_wide` (`source="fallback"`) on API failure.

#### Request Body
```json
{
  "fixture": "rest_api",
  "mission": "Build and validate a secure REST API",
  "use_gemini": false
}
```

#### Response (200 OK)
```json
{
  "mission_id": "mission-019581",
  "mission": "Build and validate a secure REST API",
  "tasks": [
    {
      "id": "t1",
      "name": "Analyze requirements",
      "required_skill": "backend",
      "est_time": 4.0,
      "est_cost": 8.0,
      "priority": "high",
      "deps": [],
      "status": "blocked"
    },
    {
      "id": "t2",
      "name": "Design architecture",
      "required_skill": "backend",
      "est_time": 6.0,
      "est_cost": 12.0,
      "priority": "high",
      "deps": [
        "t1"
      ],
      "status": "blocked"
    },
    {
      "id": "t3",
      "name": "Design database schema",
      "required_skill": "database",
      "est_time": 5.0,
      "est_cost": 10.0,
      "priority": "medium",
      "deps": [
        "t1"
      ],
      "status": "blocked"
    },
    {
      "id": "t4",
      "name": "Research security",
      "required_skill": "security",
      "est_time": 3.0,
      "est_cost": 9.0,
      "priority": "medium",
      "deps": [
        "t1"
      ],
      "status": "blocked"
    },
    {
      "id": "t5",
      "name": "Implement backend",
      "required_skill": "backend",
      "est_time": 10.0,
      "est_cost": 20.0,
      "priority": "high",
      "deps": [
        "t2",
        "t3"
      ],
      "status": "blocked"
    },
    {
      "id": "t6",
      "name": "Run security checks",
      "required_skill": "security",
      "est_time": 4.0,
      "est_cost": 12.0,
      "priority": "high",
      "deps": [
        "t4",
        "t5"
      ],
      "status": "blocked"
    },
    {
      "id": "t7",
      "name": "Write and run tests",
      "required_skill": "testing",
      "est_time": 6.0,
      "est_cost": 9.0,
      "priority": "high",
      "deps": [
        "t5"
      ],
      "status": "blocked"
    },
    {
      "id": "t8",
      "name": "Final review",
      "required_skill": "backend",
      "est_time": 3.0,
      "est_cost": 6.0,
      "priority": "low",
      "deps": [
        "t6",
        "t7"
      ],
      "status": "blocked"
    }
  ],
  "agents": [
    {
      "id": "a1",
      "name": "Backend Agent",
      "skills": [
        "backend",
        "database"
      ],
      "speed": 1.0,
      "cost_per_unit": 2.0,
      "available": true,
      "current_task": null
    },
    {
      "id": "a2",
      "name": "Security Agent",
      "skills": [
        "security",
        "backend"
      ],
      "speed": 0.9,
      "cost_per_unit": 3.0,
      "available": true,
      "current_task": null
    },
    {
      "id": "a3",
      "name": "QA Agent",
      "skills": [
        "testing",
        "security"
      ],
      "speed": 1.2,
      "cost_per_unit": 1.5,
      "available": true,
      "current_task": null
    }
  ],
  "schedule": {
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a1",
        "start_time": 0.0,
        "end_time": 4.0
      },
      {
        "task_id": "t2",
        "agent_id": "a2",
        "start_time": 4.0,
        "end_time": 10.666666666666666
      },
      {
        "task_id": "t3",
        "agent_id": "a1",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t4",
        "agent_id": "a3",
        "start_time": 4.0,
        "end_time": 6.5
      },
      {
        "task_id": "t5",
        "agent_id": "a2",
        "start_time": 10.666666666666666,
        "end_time": 21.77777777777778
      },
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 21.77777777777778,
        "end_time": 25.11111111111111
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 25.11111111111111,
        "end_time": 30.11111111111111
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 30.11111111111111,
        "end_time": 33.111111111111114
      }
    ],
    "makespan": 33.111111111111114,
    "total_cost": 93.58333333333333
  },
  "critical_path": [
    "t1",
    "t2",
    "t5",
    "t7",
    "t8"
  ],
  "cpm_details": {
    "t1": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 0.0,
      "lf": 4.0,
      "float": 0.0,
      "critical": true
    },
    "t2": {
      "es": 4.0,
      "ef": 10.0,
      "ls": 4.0,
      "lf": 10.0,
      "float": 0.0,
      "critical": true
    },
    "t3": {
      "es": 4.0,
      "ef": 9.0,
      "ls": 5.0,
      "lf": 10.0,
      "float": 1.0,
      "critical": false
    },
    "t4": {
      "es": 4.0,
      "ef": 7.0,
      "ls": 19.0,
      "lf": 22.0,
      "float": 15.0,
      "critical": false
    },
    "t5": {
      "es": 10.0,
      "ef": 20.0,
      "ls": 10.0,
      "lf": 20.0,
      "float": 0.0,
      "critical": true
    },
    "t6": {
      "es": 20.0,
      "ef": 24.0,
      "ls": 22.0,
      "lf": 26.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 20.0,
      "ef": 26.0,
      "ls": 20.0,
      "lf": 26.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 26.0,
      "ef": 29.0,
      "ls": 26.0,
      "lf": 29.0,
      "float": 0.0,
      "critical": true
    }
  },
  "makespan": 33.111111111111114,
  "total_cost": 93.58333333333333,
  "source": "rest_api"
}
```

#### Error Responses
- **422 Unprocessable Entity**: Missing `fixture` when `use_gemini=false`, or unsupported fixture name.
- **Note**: When `use_gemini=true`, any API, validation, or network failures are caught internally and gracefully fall back to `demo_wide` with `source="fallback"` (never returns a 5xx error to the client).

---

### 4. Start Mission
`POST /mission/start`

Launches worker tasks for all available agents and begins mission execution.

#### Response (200 OK)
```json
{
  "status": "running",
  "mission_id": "mission-50ed59",
  "message": "Mission started"
}
```

#### Error Responses
- **404 Not Found**: Raised if no mission has been initialized via `POST /mission`.
- **409 Conflict**: Raised if the mission is already running or has already reached terminal status.

---

### 5. Dynamic Runtime Events
`POST /event`

Injects dynamic perturbations during mission execution (`agent_failure`, `budget_cut`, `task_added`).

#### Agent Failure Request
```json
{
  "type": "agent_failure",
  "agent_id": "a1"
}
```
#### Response (200 OK)
```json
{
  "status": "ok",
  "event": {
    "type": "agent_failure",
    "agent_id": "a1",
    "new_budget": null,
    "task": null
  }
}
```

#### Budget Cut Request
```json
{
  "type": "budget_cut",
  "new_budget": 2.5
}
```
#### Response (200 OK)
```json
{
  "status": "ok",
  "event": {
    "type": "budget_cut",
    "agent_id": null,
    "new_budget": 2.5,
    "task": null
  }
}
```

#### Task Added Request
```json
{
  "type": "task_added",
  "task": {
    "id": "t_extra",
    "name": "Generate API documentation",
    "required_skill": "backend",
    "est_time": 1,
    "est_cost": 2,
    "priority": "low",
    "deps": [
      "t1"
    ],
    "status": "blocked"
  }
}
```
#### Response (200 OK)
```json
{
  "status": "ok",
  "event": {
    "type": "task_added",
    "agent_id": null,
    "new_budget": null,
    "task": {
      "id": "t_extra",
      "name": "Generate API documentation",
      "required_skill": "backend",
      "est_time": 1,
      "est_cost": 2,
      "priority": "low",
      "deps": [
        "t1"
      ],
      "status": "blocked"
    }
  }
}
```

#### Error Mapping
- **404 Not Found**: Unknown `agent_id` or no active mission.
- **409 Conflict**: Mission is not in running state, agent is already dead, or task ID is duplicate.
- **422 Unprocessable Entity**: Missing required fields, cycle detected in dependencies, or unknown dependency IDs.

---

### 6. Speed Control
`POST /speed`

Updates the simulation speed multiplier mid-run. Valid range is `[0.25, 4.0]`.

#### Request Body
```json
{
  "multiplier": 2.0
}
```

#### Response (200 OK)
```json
{
  "multiplier": 2.0,
  "status": "ok"
}
```

#### Error Responses
- **404 Not Found**: No active mission.
- **422 Unprocessable Entity**: Multiplier outside `[0.25, 4.0]`.

---

### 7. State Snapshot
`GET /state`

Returns a full snapshot of the current mission state, agent rosters, task statuses, CPM critical path, and recent event logs.

#### Response (200 OK)
```json
{
  "type": "snapshot",
  "mission": "Build and validate a secure REST API",
  "status": "idle",
  "failed_reason": null,
  "t": 0.0,
  "sim_time": 0.0,
  "seq": 1,
  "last_seq": 1,
  "agents": [
    {
      "id": "a1",
      "name": "Backend Agent",
      "skills": [
        "backend",
        "database"
      ],
      "speed": 1.0,
      "cost_per_unit": 2.0,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    },
    {
      "id": "a2",
      "name": "Security Agent",
      "skills": [
        "security",
        "backend"
      ],
      "speed": 0.9,
      "cost_per_unit": 3.0,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    },
    {
      "id": "a3",
      "name": "QA Agent",
      "skills": [
        "testing",
        "security"
      ],
      "speed": 1.2,
      "cost_per_unit": 1.5,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    }
  ],
  "tasks": [
    {
      "id": "t1",
      "name": "Analyze requirements",
      "required_skill": "backend",
      "deps": [],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 0.0,
      "end_t": 4.0
    },
    {
      "id": "t2",
      "name": "Design architecture",
      "required_skill": "backend",
      "deps": [
        "t1"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a2",
      "start_t": 4.0,
      "end_t": 10.666666666666666
    },
    {
      "id": "t3",
      "name": "Design database schema",
      "required_skill": "database",
      "deps": [
        "t1"
      ],
      "priority": "medium",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 4.0,
      "end_t": 9.0
    },
    {
      "id": "t4",
      "name": "Research security",
      "required_skill": "security",
      "deps": [
        "t1"
      ],
      "priority": "medium",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 4.0,
      "end_t": 6.5
    },
    {
      "id": "t5",
      "name": "Implement backend",
      "required_skill": "backend",
      "deps": [
        "t2",
        "t3"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a2",
      "start_t": 10.666666666666666,
      "end_t": 21.77777777777778
    },
    {
      "id": "t6",
      "name": "Run security checks",
      "required_skill": "security",
      "deps": [
        "t4",
        "t5"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 21.77777777777778,
      "end_t": 25.11111111111111
    },
    {
      "id": "t7",
      "name": "Write and run tests",
      "required_skill": "testing",
      "deps": [
        "t5"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 25.11111111111111,
      "end_t": 30.11111111111111
    },
    {
      "id": "t8",
      "name": "Final review",
      "required_skill": "backend",
      "deps": [
        "t6",
        "t7"
      ],
      "priority": "low",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 30.11111111111111,
      "end_t": 33.111111111111114
    }
  ],
  "current_schedule": {
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a1",
        "start_time": 0.0,
        "end_time": 4.0
      },
      {
        "task_id": "t2",
        "agent_id": "a2",
        "start_time": 4.0,
        "end_time": 10.666666666666666
      },
      {
        "task_id": "t3",
        "agent_id": "a1",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t4",
        "agent_id": "a3",
        "start_time": 4.0,
        "end_time": 6.5
      },
      {
        "task_id": "t5",
        "agent_id": "a2",
        "start_time": 10.666666666666666,
        "end_time": 21.77777777777778
      },
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 21.77777777777778,
        "end_time": 25.11111111111111
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 25.11111111111111,
        "end_time": 30.11111111111111
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 30.11111111111111,
        "end_time": 33.111111111111114
      }
    ],
    "makespan": 33.111111111111114,
    "total_cost": 93.58333333333333
  },
  "critical_path": [
    "t1",
    "t2",
    "t5",
    "t7",
    "t8"
  ],
  "cpm_details": {
    "t1": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 0.0,
      "lf": 4.0,
      "float": 0.0,
      "critical": true
    },
    "t2": {
      "es": 4.0,
      "ef": 10.0,
      "ls": 4.0,
      "lf": 10.0,
      "float": 0.0,
      "critical": true
    },
    "t3": {
      "es": 4.0,
      "ef": 9.0,
      "ls": 5.0,
      "lf": 10.0,
      "float": 1.0,
      "critical": false
    },
    "t4": {
      "es": 4.0,
      "ef": 7.0,
      "ls": 19.0,
      "lf": 22.0,
      "float": 15.0,
      "critical": false
    },
    "t5": {
      "es": 10.0,
      "ef": 20.0,
      "ls": 10.0,
      "lf": 20.0,
      "float": 0.0,
      "critical": true
    },
    "t6": {
      "es": 20.0,
      "ef": 24.0,
      "ls": 22.0,
      "lf": 26.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 20.0,
      "ef": 26.0,
      "ls": 20.0,
      "lf": 26.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 26.0,
      "ef": 29.0,
      "ls": 26.0,
      "lf": 29.0,
      "float": 0.0,
      "critical": true
    }
  },
  "events": [
    {
      "seq": 1,
      "type": "plan_created",
      "t": 0.0,
      "schedule": {
        "assignments": [
          {
            "task_id": "t1",
            "agent_id": "a1",
            "start_time": 0.0,
            "end_time": 4.0
          },
          {
            "task_id": "t2",
            "agent_id": "a2",
            "start_time": 4.0,
            "end_time": 10.666666666666666
          },
          {
            "task_id": "t3",
            "agent_id": "a1",
            "start_time": 4.0,
            "end_time": 9.0
          },
          {
            "task_id": "t4",
            "agent_id": "a3",
            "start_time": 4.0,
            "end_time": 6.5
          },
          {
            "task_id": "t5",
            "agent_id": "a2",
            "start_time": 10.666666666666666,
            "end_time": 21.77777777777778
          },
          {
            "task_id": "t6",
            "agent_id": "a3",
            "start_time": 21.77777777777778,
            "end_time": 25.11111111111111
          },
          {
            "task_id": "t7",
            "agent_id": "a3",
            "start_time": 25.11111111111111,
            "end_time": 30.11111111111111
          },
          {
            "task_id": "t8",
            "agent_id": "a1",
            "start_time": 30.11111111111111,
            "end_time": 33.111111111111114
          }
        ],
        "makespan": 33.111111111111114,
        "total_cost": 93.58333333333333
      },
      "makespan": 33.111111111111114,
      "total_cost": 93.58333333333333,
      "cpm_details": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      },
      "cpm": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      }
    }
  ],
  "event_log": [
    {
      "seq": 1,
      "type": "plan_created",
      "t": 0.0,
      "schedule": {
        "assignments": [
          {
            "task_id": "t1",
            "agent_id": "a1",
            "start_time": 0.0,
            "end_time": 4.0
          },
          {
            "task_id": "t2",
            "agent_id": "a2",
            "start_time": 4.0,
            "end_time": 10.666666666666666
          },
          {
            "task_id": "t3",
            "agent_id": "a1",
            "start_time": 4.0,
            "end_time": 9.0
          },
          {
            "task_id": "t4",
            "agent_id": "a3",
            "start_time": 4.0,
            "end_time": 6.5
          },
          {
            "task_id": "t5",
            "agent_id": "a2",
            "start_time": 10.666666666666666,
            "end_time": 21.77777777777778
          },
          {
            "task_id": "t6",
            "agent_id": "a3",
            "start_time": 21.77777777777778,
            "end_time": 25.11111111111111
          },
          {
            "task_id": "t7",
            "agent_id": "a3",
            "start_time": 25.11111111111111,
            "end_time": 30.11111111111111
          },
          {
            "task_id": "t8",
            "agent_id": "a1",
            "start_time": 30.11111111111111,
            "end_time": 33.111111111111114
          }
        ],
        "makespan": 33.111111111111114,
        "total_cost": 93.58333333333333
      },
      "makespan": 33.111111111111114,
      "total_cost": 93.58333333333333,
      "cpm_details": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      },
      "cpm": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      }
    }
  ]
}
```

---

### 8. Final Report
`GET /report`

Provides the final execution report including total simulated time, actual cost, wasted cost, and failures recovered.

#### Response (200 OK)
```json
{
  "mission_id": "mission-0355bf",
  "mission": "Build and validate a secure REST API",
  "status": "idle",
  "total_time": 0.0,
  "actual_cost": 0.0,
  "wasted_cost": 0.0,
  "failures_recovered": 0,
  "tasks_total": 8,
  "tasks_done": 0,
  "failed_reason": null
}
```

#### Error Responses
- **404 Not Found**: No mission has been initialized.

---

## WebSocket Telemetry (`/ws`)

Clients connecting to `/ws` immediately receive a `snapshot` event, followed by a real-time stream of all engine events. Dead sockets are silently dropped without interrupting mission execution.

### Event Schema Invariant
Every message conforms to `schemas/event.schema.json`:
- `type` (string, required): The event name.
- `t` (number, required): Simulated timestamp at event emission.
- `seq` (integer, required): Monotonically increasing sequence identifier.
- Optional fields: `task_id`, `agent_id`, and event-specific payloads.

---

### Real Event Payloads

#### 1. `snapshot`
Sent immediately upon WebSocket connection and returned by `GET /state`.
```json
{
  "type": "snapshot",
  "mission": "Build and validate a secure REST API",
  "status": "idle",
  "failed_reason": null,
  "t": 0.0,
  "sim_time": 0.0,
  "seq": 1,
  "last_seq": 1,
  "agents": [
    {
      "id": "a1",
      "name": "Backend Agent",
      "skills": [
        "backend",
        "database"
      ],
      "speed": 1.0,
      "cost_per_unit": 2.0,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    },
    {
      "id": "a2",
      "name": "Security Agent",
      "skills": [
        "security",
        "backend"
      ],
      "speed": 0.9,
      "cost_per_unit": 3.0,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    },
    {
      "id": "a3",
      "name": "QA Agent",
      "skills": [
        "testing",
        "security"
      ],
      "speed": 1.2,
      "cost_per_unit": 1.5,
      "status": "idle",
      "current_task": null,
      "tasks_done": 0
    }
  ],
  "tasks": [
    {
      "id": "t1",
      "name": "Analyze requirements",
      "required_skill": "backend",
      "deps": [],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 0.0,
      "end_t": 4.0
    },
    {
      "id": "t2",
      "name": "Design architecture",
      "required_skill": "backend",
      "deps": [
        "t1"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a2",
      "start_t": 4.0,
      "end_t": 10.666666666666666
    },
    {
      "id": "t3",
      "name": "Design database schema",
      "required_skill": "database",
      "deps": [
        "t1"
      ],
      "priority": "medium",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 4.0,
      "end_t": 9.0
    },
    {
      "id": "t4",
      "name": "Research security",
      "required_skill": "security",
      "deps": [
        "t1"
      ],
      "priority": "medium",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 4.0,
      "end_t": 6.5
    },
    {
      "id": "t5",
      "name": "Implement backend",
      "required_skill": "backend",
      "deps": [
        "t2",
        "t3"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a2",
      "start_t": 10.666666666666666,
      "end_t": 21.77777777777778
    },
    {
      "id": "t6",
      "name": "Run security checks",
      "required_skill": "security",
      "deps": [
        "t4",
        "t5"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 21.77777777777778,
      "end_t": 25.11111111111111
    },
    {
      "id": "t7",
      "name": "Write and run tests",
      "required_skill": "testing",
      "deps": [
        "t5"
      ],
      "priority": "high",
      "status": "blocked",
      "agent_id": "a3",
      "start_t": 25.11111111111111,
      "end_t": 30.11111111111111
    },
    {
      "id": "t8",
      "name": "Final review",
      "required_skill": "backend",
      "deps": [
        "t6",
        "t7"
      ],
      "priority": "low",
      "status": "blocked",
      "agent_id": "a1",
      "start_t": 30.11111111111111,
      "end_t": 33.111111111111114
    }
  ],
  "current_schedule": {
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a1",
        "start_time": 0.0,
        "end_time": 4.0
      },
      {
        "task_id": "t2",
        "agent_id": "a2",
        "start_time": 4.0,
        "end_time": 10.666666666666666
      },
      {
        "task_id": "t3",
        "agent_id": "a1",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t4",
        "agent_id": "a3",
        "start_time": 4.0,
        "end_time": 6.5
      },
      {
        "task_id": "t5",
        "agent_id": "a2",
        "start_time": 10.666666666666666,
        "end_time": 21.77777777777778
      },
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 21.77777777777778,
        "end_time": 25.11111111111111
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 25.11111111111111,
        "end_time": 30.11111111111111
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 30.11111111111111,
        "end_time": 33.111111111111114
      }
    ],
    "makespan": 33.111111111111114,
    "total_cost": 93.58333333333333
  },
  "critical_path": [
    "t1",
    "t2",
    "t5",
    "t7",
    "t8"
  ],
  "cpm_details": {
    "t1": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 0.0,
      "lf": 4.0,
      "float": 0.0,
      "critical": true
    },
    "t2": {
      "es": 4.0,
      "ef": 10.0,
      "ls": 4.0,
      "lf": 10.0,
      "float": 0.0,
      "critical": true
    },
    "t3": {
      "es": 4.0,
      "ef": 9.0,
      "ls": 5.0,
      "lf": 10.0,
      "float": 1.0,
      "critical": false
    },
    "t4": {
      "es": 4.0,
      "ef": 7.0,
      "ls": 19.0,
      "lf": 22.0,
      "float": 15.0,
      "critical": false
    },
    "t5": {
      "es": 10.0,
      "ef": 20.0,
      "ls": 10.0,
      "lf": 20.0,
      "float": 0.0,
      "critical": true
    },
    "t6": {
      "es": 20.0,
      "ef": 24.0,
      "ls": 22.0,
      "lf": 26.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 20.0,
      "ef": 26.0,
      "ls": 20.0,
      "lf": 26.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 26.0,
      "ef": 29.0,
      "ls": 26.0,
      "lf": 29.0,
      "float": 0.0,
      "critical": true
    }
  },
  "events": [
    {
      "seq": 1,
      "type": "plan_created",
      "t": 0.0,
      "schedule": {
        "assignments": [
          {
            "task_id": "t1",
            "agent_id": "a1",
            "start_time": 0.0,
            "end_time": 4.0
          },
          {
            "task_id": "t2",
            "agent_id": "a2",
            "start_time": 4.0,
            "end_time": 10.666666666666666
          },
          {
            "task_id": "t3",
            "agent_id": "a1",
            "start_time": 4.0,
            "end_time": 9.0
          },
          {
            "task_id": "t4",
            "agent_id": "a3",
            "start_time": 4.0,
            "end_time": 6.5
          },
          {
            "task_id": "t5",
            "agent_id": "a2",
            "start_time": 10.666666666666666,
            "end_time": 21.77777777777778
          },
          {
            "task_id": "t6",
            "agent_id": "a3",
            "start_time": 21.77777777777778,
            "end_time": 25.11111111111111
          },
          {
            "task_id": "t7",
            "agent_id": "a3",
            "start_time": 25.11111111111111,
            "end_time": 30.11111111111111
          },
          {
            "task_id": "t8",
            "agent_id": "a1",
            "start_time": 30.11111111111111,
            "end_time": 33.111111111111114
          }
        ],
        "makespan": 33.111111111111114,
        "total_cost": 93.58333333333333
      },
      "makespan": 33.111111111111114,
      "total_cost": 93.58333333333333,
      "cpm_details": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      },
      "cpm": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      }
    }
  ],
  "event_log": [
    {
      "seq": 1,
      "type": "plan_created",
      "t": 0.0,
      "schedule": {
        "assignments": [
          {
            "task_id": "t1",
            "agent_id": "a1",
            "start_time": 0.0,
            "end_time": 4.0
          },
          {
            "task_id": "t2",
            "agent_id": "a2",
            "start_time": 4.0,
            "end_time": 10.666666666666666
          },
          {
            "task_id": "t3",
            "agent_id": "a1",
            "start_time": 4.0,
            "end_time": 9.0
          },
          {
            "task_id": "t4",
            "agent_id": "a3",
            "start_time": 4.0,
            "end_time": 6.5
          },
          {
            "task_id": "t5",
            "agent_id": "a2",
            "start_time": 10.666666666666666,
            "end_time": 21.77777777777778
          },
          {
            "task_id": "t6",
            "agent_id": "a3",
            "start_time": 21.77777777777778,
            "end_time": 25.11111111111111
          },
          {
            "task_id": "t7",
            "agent_id": "a3",
            "start_time": 25.11111111111111,
            "end_time": 30.11111111111111
          },
          {
            "task_id": "t8",
            "agent_id": "a1",
            "start_time": 30.11111111111111,
            "end_time": 33.111111111111114
          }
        ],
        "makespan": 33.111111111111114,
        "total_cost": 93.58333333333333
      },
      "makespan": 33.111111111111114,
      "total_cost": 93.58333333333333,
      "cpm_details": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      },
      "cpm": {
        "t1": {
          "es": 0.0,
          "ef": 4.0,
          "ls": 0.0,
          "lf": 4.0,
          "float": 0.0,
          "critical": true
        },
        "t2": {
          "es": 4.0,
          "ef": 10.0,
          "ls": 4.0,
          "lf": 10.0,
          "float": 0.0,
          "critical": true
        },
        "t3": {
          "es": 4.0,
          "ef": 9.0,
          "ls": 5.0,
          "lf": 10.0,
          "float": 1.0,
          "critical": false
        },
        "t4": {
          "es": 4.0,
          "ef": 7.0,
          "ls": 19.0,
          "lf": 22.0,
          "float": 15.0,
          "critical": false
        },
        "t5": {
          "es": 10.0,
          "ef": 20.0,
          "ls": 10.0,
          "lf": 20.0,
          "float": 0.0,
          "critical": true
        },
        "t6": {
          "es": 20.0,
          "ef": 24.0,
          "ls": 22.0,
          "lf": 26.0,
          "float": 2.0,
          "critical": false
        },
        "t7": {
          "es": 20.0,
          "ef": 26.0,
          "ls": 20.0,
          "lf": 26.0,
          "float": 0.0,
          "critical": true
        },
        "t8": {
          "es": 26.0,
          "ef": 29.0,
          "ls": 26.0,
          "lf": 29.0,
          "float": 0.0,
          "critical": true
        }
      }
    }
  ]
}
```

#### 2. `plan_created`
Emitted when the initial greedy plan and critical path are computed.
```json
{
  "seq": 1,
  "type": "plan_created",
  "t": 0.0,
  "schedule": {
    "assignments": [
      {
        "task_id": "t1",
        "agent_id": "a1",
        "start_time": 0.0,
        "end_time": 4.0
      },
      {
        "task_id": "t2",
        "agent_id": "a2",
        "start_time": 4.0,
        "end_time": 10.666666666666666
      },
      {
        "task_id": "t3",
        "agent_id": "a1",
        "start_time": 4.0,
        "end_time": 9.0
      },
      {
        "task_id": "t4",
        "agent_id": "a3",
        "start_time": 4.0,
        "end_time": 6.5
      },
      {
        "task_id": "t5",
        "agent_id": "a2",
        "start_time": 10.666666666666666,
        "end_time": 21.77777777777778
      },
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 21.77777777777778,
        "end_time": 25.11111111111111
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 25.11111111111111,
        "end_time": 30.11111111111111
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 30.11111111111111,
        "end_time": 33.111111111111114
      }
    ],
    "makespan": 33.111111111111114,
    "total_cost": 93.58333333333333
  },
  "makespan": 33.111111111111114,
  "total_cost": 93.58333333333333,
  "cpm_details": {
    "t1": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 0.0,
      "lf": 4.0,
      "float": 0.0,
      "critical": true
    },
    "t2": {
      "es": 4.0,
      "ef": 10.0,
      "ls": 4.0,
      "lf": 10.0,
      "float": 0.0,
      "critical": true
    },
    "t3": {
      "es": 4.0,
      "ef": 9.0,
      "ls": 5.0,
      "lf": 10.0,
      "float": 1.0,
      "critical": false
    },
    "t4": {
      "es": 4.0,
      "ef": 7.0,
      "ls": 19.0,
      "lf": 22.0,
      "float": 15.0,
      "critical": false
    },
    "t5": {
      "es": 10.0,
      "ef": 20.0,
      "ls": 10.0,
      "lf": 20.0,
      "float": 0.0,
      "critical": true
    },
    "t6": {
      "es": 20.0,
      "ef": 24.0,
      "ls": 22.0,
      "lf": 26.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 20.0,
      "ef": 26.0,
      "ls": 20.0,
      "lf": 26.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 26.0,
      "ef": 29.0,
      "ls": 26.0,
      "lf": 29.0,
      "float": 0.0,
      "critical": true
    }
  },
  "cpm": {
    "t1": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 0.0,
      "lf": 4.0,
      "float": 0.0,
      "critical": true
    },
    "t2": {
      "es": 4.0,
      "ef": 10.0,
      "ls": 4.0,
      "lf": 10.0,
      "float": 0.0,
      "critical": true
    },
    "t3": {
      "es": 4.0,
      "ef": 9.0,
      "ls": 5.0,
      "lf": 10.0,
      "float": 1.0,
      "critical": false
    },
    "t4": {
      "es": 4.0,
      "ef": 7.0,
      "ls": 19.0,
      "lf": 22.0,
      "float": 15.0,
      "critical": false
    },
    "t5": {
      "es": 10.0,
      "ef": 20.0,
      "ls": 10.0,
      "lf": 20.0,
      "float": 0.0,
      "critical": true
    },
    "t6": {
      "es": 20.0,
      "ef": 24.0,
      "ls": 22.0,
      "lf": 26.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 20.0,
      "ef": 26.0,
      "ls": 20.0,
      "lf": 26.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 26.0,
      "ef": 29.0,
      "ls": 26.0,
      "lf": 29.0,
      "float": 0.0,
      "critical": true
    }
  }
}
```

#### 3. `mission_started`
Emitted when worker execution loops begin.
```json
{
  "seq": 2,
  "type": "mission_started",
  "t": 0.0,
  "mission_id": "mission-bf6ab7"
}
```

#### 4. `task_started`
Emitted when an agent worker claims and begins executing a task.
```json
{
  "seq": 3,
  "type": "task_started",
  "t": 0.0,
  "task_id": "t1",
  "agent_id": "a1",
  "duration": 4.0,
  "est_end_t": 4.0
}
```

#### 5. `task_done`
Emitted when an agent worker completes a task.
```json
{
  "seq": 16,
  "type": "task_done",
  "t": 5.875000002561137,
  "task_id": "t_extra",
  "agent_id": "a2"
}
```

#### 6. `task_failed`
Emitted when an executing task is aborted due to an agent failure, recording wasted cost.
```json
{
  "seq": 4,
  "type": "task_failed",
  "t": 0.0940000000409782,
  "task_id": "t1",
  "agent_id": "a1",
  "wasted_cost": 0.24000000000000002,
  "partial_cost": 0.24000000000000002
}
```

#### 7. `agent_failed`
Emitted when an agent crashes or is decommissioned.
```json
{
  "seq": 5,
  "type": "agent_failed",
  "t": 0.0940000000409782,
  "agent_id": "a1",
  "interrupted_task": "t1"
}
```

#### 8. `replanned`
Emitted after dynamic re-optimization completes following failure recovery, budget cut, or task addition.
```json
{
  "seq": 17,
  "type": "replanned",
  "t": 5.875000002561137,
  "schedule": {
    "assignments": [
      {
        "task_id": "t6",
        "agent_id": "a3",
        "start_time": 0.0,
        "end_time": 3.3333333333333335
      },
      {
        "task_id": "t7",
        "agent_id": "a3",
        "start_time": 3.3333333333333335,
        "end_time": 8.333333333333334
      },
      {
        "task_id": "t8",
        "agent_id": "a1",
        "start_time": 8.333333333333334,
        "end_time": 11.333333333333334
      }
    ],
    "makespan": 11.333333333333334,
    "total_cost": 18.5
  },
  "task_status": {
    "t1": "done",
    "t2": "done",
    "t3": "done",
    "t4": "done",
    "t5": "running",
    "t6": "blocked",
    "t7": "blocked",
    "t8": "blocked",
    "t_extra": "done"
  },
  "reassigned_task_ids": [
    "t6",
    "t7",
    "t8"
  ],
  "total_cost": 18.5,
  "projected_finish_t": 17.208333335894473,
  "cpm_details": {
    "t6": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 2.0,
      "lf": 6.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 0.0,
      "ef": 6.0,
      "ls": 0.0,
      "lf": 6.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 6.0,
      "ef": 9.0,
      "ls": 6.0,
      "lf": 9.0,
      "float": 0.0,
      "critical": true
    }
  },
  "cpm": {
    "t6": {
      "es": 0.0,
      "ef": 4.0,
      "ls": 2.0,
      "lf": 6.0,
      "float": 2.0,
      "critical": false
    },
    "t7": {
      "es": 0.0,
      "ef": 6.0,
      "ls": 0.0,
      "lf": 6.0,
      "float": 0.0,
      "critical": true
    },
    "t8": {
      "es": 6.0,
      "ef": 9.0,
      "ls": 6.0,
      "lf": 9.0,
      "float": 0.0,
      "critical": true
    }
  }
}
```

#### 9. `mission_done`
Emitted upon successful completion of all mission tasks.
```json
{
  "seq": 20,
  "type": "mission_done",
  "t": 49.60000002756715,
  "total_time": 49.60000002756715,
  "duration": 49.60000002756715,
  "actual_cost": 93.58333333333333,
  "wasted_cost": 0.0,
  "failures_recovered": 0
}
```

#### 10. `mission_failed`
Emitted when pending tasks cannot be scheduled due to skill deficits or resource exhaustion.
```json
{
  "seq": 5,
  "type": "mission_failed",
  "t": 0.0,
  "reason": "Unassignable tasks: t7, t8",
  "unassignable_tasks": [
    "t7",
    "t8"
  ],
  "unassignable_task_ids": [
    "t7",
    "t8"
  ]
}
```

#### 11. `task_added`
Emitted when a new task is dynamically introduced to the DAG.
```json
{
  "seq": 11,
  "type": "task_added",
  "t": 5.875000002561137,
  "task": {
    "id": "t_extra",
    "name": "Generate API documentation",
    "required_skill": "backend",
    "est_time": 1.0,
    "est_cost": 2.0,
    "priority": "low",
    "deps": [
      "t1"
    ],
    "status": "ready"
  }
}
```

#### 12. `speed_changed`
Emitted when simulation clock speed is adjusted.
```json
{
  "seq": 4,
  "type": "speed_changed",
  "t": 0.0,
  "multiplier": 2.5
}
```
