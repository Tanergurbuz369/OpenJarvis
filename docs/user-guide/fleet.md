# Agent Fleet

The fleet is OpenJarvis's automatic multi-agent orchestration layer: a catalog
of **90+ specialist agent roles** (software, research, data, content,
marketing, sales, finance, operations, legal, design, education, personal
assistance, ...) that are activated **on demand**. You give the fleet one
objective; it plans, staffs, and executes the work with a team of agents — on
your local model by default, so it costs nothing to run.

## How a mission runs

```
objective ─▶ Mission Planner (LLM) decomposes into subtasks
          ─▶ Dispatcher assigns each subtask the best-suited specialist
          ─▶ Subtasks execute in parallel dependency stages
          ─▶ Chief of Staff synthesizes one final deliverable
```

- **Roles are cheap.** A role is just a blueprint (system prompt + keywords +
  optional tools). Only the roles a mission actually needs are instantiated as
  live agents, so the catalog can be arbitrarily large.
- **Automatic staffing.** The planner names a specialist per subtask; if it
  names an unknown role, a keyword dispatcher picks the closest match. With no
  LLM available, the dispatcher alone routes the whole objective to the single
  best specialist.
- **Parallel by default.** Independent subtasks run concurrently
  (`max_parallel`, default 4); `depends_on` edges create sequential stages,
  and downstream agents receive their teammates' outputs as context.
- **Tools when useful.** Roles that declare tools (e.g. `web_search`,
  `code_interpreter`) run as tool-using orchestrator agents; the rest run as
  fast single-turn specialists.

## Desktop UI

Open the **Fleet** page in the sidebar:

- launch missions and watch specialists activate, work, and finish live
  (via the `fleet_*` WebSocket events),
- inspect each subtask's output and the final deliverable,
- browse and search the full specialist catalog by category.

## API

| Endpoint | Description |
|---|---|
| `GET /v1/fleet/status` | Role count, categories, active missions |
| `GET /v1/fleet/roles?q=&category=` | Browse/search the catalog |
| `GET /v1/fleet/roles/match?task=...` | Preview dispatcher picks for a task |
| `POST /v1/fleet/missions` | Launch a mission (`{"objective": "..."}`) |
| `GET /v1/fleet/missions` | Mission history |
| `GET /v1/fleet/missions/{id}` | Mission detail incl. subtasks |
| `POST /v1/fleet/missions/{id}/cancel` | Request cancellation |

## Python SDK

```python
from openjarvis.fleet import FleetCoordinator

coordinator = FleetCoordinator(engine, model)
mission = coordinator.run_mission_sync(
    "Research the local-AI market and draft a launch blog post"
)
print(mission.status)          # MissionStatus.COMPLETED
for st in mission.subtasks:    # who did what
    print(st.role_id, st.status, st.title)
print(mission.final_output)    # synthesized deliverable
```

`FleetCoordinator.submit(objective)` does the same asynchronously on a
background thread and returns the mission immediately; poll
`coordinator.store.get(mission_id)` or subscribe to the `FLEET_*` events on
the event bus.

## Custom roles

Drop TOML files into `~/.openjarvis/fleet/roles/` — they appear in the catalog
and dispatcher immediately (restart the server to reload):

```toml
[role]
role_id = "wine_sommelier"
name = "Wine Sommelier"
category = "personal"
icon = "🍷"
description = "Recommends wine pairings and cellar picks."
keywords = ["wine", "pairing", "sommelier", "vineyard"]
system_prompt = "You are an expert sommelier. Recommend pairings with reasons."
tools = ["web_search"]
```

Unknown tool names are skipped gracefully, so a role degrades to a pure-LLM
specialist when a tool isn't available on the machine.

## Events

The fleet publishes `FLEET_MISSION_START`, `FLEET_MISSION_PLANNED`,
`FLEET_TASK_START`, `FLEET_TASK_END`, and `FLEET_MISSION_END` on the core
event bus, all bridged to the `/v1/agents/events` WebSocket for real-time
UIs.
