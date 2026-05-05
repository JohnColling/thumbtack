# Thumbtack Master Roadmap

> Inspired by: OpenAI Symphony, Hermes Kanban Orchestrator, Kanban Worker, and existing Thumbtack architecture.

---

## 1. Master Concept

Thumbtack is an **autonomous agent orchestrator** — not just a chat companion. Inspired by OpenAI Symphony, it will become a persistent server that:

- Monitors a task queue (backlog) on a heartbeat/polling loop
- Auto-decomposes high-level tasks into subtasks (Lego bricks) using an LLM planner
- Spawns one or more **specialist agents** in parallel to execute those subtasks
- Each agent works in its own **isolated git workspace** to prevent code clashing
- Reports results, merges outputs, and returns control to the human operator
- Operates with **minimal human input** once a plan is approved
- **Does not rely on Hermes' `delegate_task`, `kanban-orchestrator`, or `autonomous-ai-agents` skills** — this is a standalone framework within Thumbtack

**Philosophy:** A human gives one overarching goal. Thumbtack plans, delegates, executes, and reports. The human only intervenes for high-level decisions (plan approval, task rejections, final sign-off).

---

## 2. Phase 1: System Console + Heartbeat (STARTED)

| Status | 🟢 In Progress |

**Goal:** A visible "agent is alive" status in the Thumbtack UI — the foundation that everything else runs on.

**Already Done:**
- ✅ `agent_log` SQLite table + helpers
- ✅ Background asyncio heartbeat loop — wakes every 15 minutes
- ✅ `/api/agent-log` endpoint
- ✅ System Console panel in the UI (bottom of every page)
- ✅ Exception armor around heartbeat — bad tick logs error, never kills server
- ✅ systemd unit — auto-restart always (`Restart=always`), crash logging, watchdog file
- ✅ Timezone fix — Brisbane AEST timestamps throughout

**Still To Do in Phase 1:**
- [ ] Verify heartbeat keeps running overnight without crashes
- [ ] Add "Tasks" table to SQLite
- [ ] Add Task Queue UI (create/view tasks)
- [ ] Connect heartbeat to task scanning

---

## 3. Phase 2: Task Queue + Human Approval Gate

| Status | 🟡 Planned |

**Goal:** A human creates a task, Thumbtack proposes a decomposition plan, the human approves once, then subtasks are queued for execution.

**Flow:**
1. Human creates a Task via UI (title, description, priority)
2. Task status = `pending`
3. On next heartbeat, orchestrator sees `pending` task, stops, sets status = `planning`
4. Master agent (Hermes via chat, or an LLM planner inside Thumbtack) proposes X subtasks
5. Human reviews plan, approves or rejects
6. If approved: subtasks get status `queued`, parent task = `approved`
7. Orchestrator processes `queued` subtasks on subsequent ticks

**Schema (`tasks` table):**
```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 3,  -- 1=urgent, 5=low
    status TEXT DEFAULT 'pending', -- pending, planning, approved, queued, running, review, done, failed
    parent_task_id INTEGER,      -- NULL for top-level, FK to tasks(id) for subtasks
    planned_at TEXT,
    approved_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(parent_task_id) REFERENCES tasks(id)
);
```

**Key:** The `parent_task_id` column is the tree structure that lets one task have N subtasks.

---

## 4. Phase 3: Agent Worker Pool (Spawning Actual Agents)

| Status | 🔴 Not Started |

**Goal:** Thumbtack spawns real coding agents (Claude Code, Codex, OpenCode, etc.) as subprocesses, each working in its own per-task git workspace.

**Architecture:**

```
ThumbTack Server (FastAPI, persistent)
  |
  ├── Orchestrator Loop (asyncio, every 15 min)
  │     ├── Scan task queue
  │     ├── Check agent slots
  │     ├── Pick N tasks to run in parallel
  │     │
  │     └── Agent Worker Launcher
  │           ├── Create per-task workspace
  │           │   └── git clone <project-repo> /workspaces/task-<id>/
  │           ├── Spawn agent process
  │           │   └── e.g. `claude code /workspaces/task-<id> "implement login form"`
  │           ├── Capture stdout/stderr (live stream to DB)
  │           └── On completion → mark subtask done, merge or report
  │
  └── REST API + WebSocket + Dashboard UI
```

**Per-task workspace rule:** Each agent gets its own working directory. If a subtask requires code changes, the agent works in `workspaces/task-<task-id>/` — a git clone of the project. This prevents two agents from editing the same file simultaneously.

**Agent types:**
- **Coder agent** (claude-code, codex) — implements features, writes code
- **Research agent** (web search enabled) — gathers docs, compares options
- **Review agent** — runs tests, linters, checks code quality
- **Deploy agent** — builds, deploys, verifies

**Integration note:** These agents are spawned via `asyncio.create_subprocess_exec` or `terminal(background=True)` with output streamed to a per-process log table.

---

## 5. Phase 4: Autonomous Pipeline (Human Out of the Loop)

| Status | 🔴 Not Started |

**Goal:** No more "what's next?" questions. Once a task is queued, Thumbtack processes it end-to-end.

**Behavior:**
- Orchestrator wakes → scans all tasks → picks top N in priority order
- Spawns agents → monitors output → marks done/failed → retries if needed
- When all subtasks are done → marks parent task `done` → notifies human
- If a task fails N times → marks parent `blocked` → human review required
- If new tasks are created while working → they get queued for NEXT tick

**Human interaction points (only these):**
1. Create high-level task
2. Approve decomposition plan
3. Final review / accept completed task
4. Unblock tasks that failed too many times

---

## 6. Token Estimation / Context Pressure Gauge

| Status | 🟡 Planned |

A UI widget showing estimated current context usage. This prevents the "am I talking funny?" degradation problem.

**Rough approximation (today):**
- English ≈ 0.75 tokens per word
- Code ≈ 1.0 tokens per word
- System prompt + memory + skills ≈ static overhead (counted once per session)
- Full payload = system prompt + history + current message

**Target:** Build a lightweight tokenizer estimate inside ThumbTack (e.g., use `tiktoken` or a fast BPE tokenizer). Pipe the raw prompt payload through it before sending to the LLM, log the count.

**Note:** A live "fuel gauge" in the UI is a Phase-2 goal. The current Hermes runtime does not expose token counts to the agent, so a third-party estimate is the only practical path.

---

## 7. External API

| Status | 🟡 Suggested |

Allow outside services to trigger agents/events inside ThumbTack.

**Minimal first step:** Add a `POST /api/webhook` endpoint guarded by a secret token. Accept a JSON payload with `task_title`, `description`, and `priority`. Create a Task record and return `201 Created`.

**Later:** Add full REST CRUD for Tasks, TaskRuns, and Subtasks, plus WebSocket streaming for live agent output.

---

## 8. Key Patterns Borrowed from Symphony

### 8.1 Workspace Isolation
- Per-task git working directory
- Agents never share a workspace
- Merge handled by orchestrator, not agents

### 8.2 `WORKFLOW.md` in Repo Root
- Version-controlled agent instructions
- YAML front matter for agent config
- Markdown body as prompt template
- Hot-reload without restart

### 8.3 Reconciliation Every Tick
- Check if running tasks are still valid
- Kill stale agents
- Clean terminal workspaces

### 8.4 Token Tracking per Session
- Live counters: input_tokens, output_tokens, total_tokens
- Aggregate in orchestrator metrics

### 8.5 Concurrency Limits
- Global: `max_concurrent_agents`
- Per-state: `max_concurrent_agents_by_state`
- Queue slots managed by heartbeat

### 8.6 Exponential Backoff Retries
- `delay = min(10000 * 2^(attempt - 1), max_backoff_ms)`
- Default max backoff = 5 minutes (300,000 ms)

### 8.7 Continuation Turns
- One agent session can do multiple back-to-back turns
- First turn gets full task prompt
- Continuation turns get only guidance (not full history resend)

### 8.8 `agent_log` Table for Observability
- One row per event
- Status dot (idle/running/error) visible in UI
- Human-readable log: `[07:22:45] Agent wake → scan → idle`

---

## 9. Monitoring & Crash Detection (No More Silent Deaths)

| Layer | Mechanism | Action |
|---|---|---|
| **Python try/except** | Heartbeat wrapped in `try` → logs to `agent_log` | Never kills server |
| **Crash logger** | Unhandled exceptions → `thumbtack-crash.log` | Debug file |
| **Watchdog file** | Touches `.alive` every tick | External monitor can check age |
| **systemd restart** | `Restart=always`, 10 attempts in 5 min | Auto-reboot loop |
| **Health endpoint** | `GET /health` → uptime + last wake | `curl` from anywhere |

---

## 10. Next Actions (Immediate Priority)

1. ✅ Heartbeat loop running → verify overnight stability
2. ⏳ Add `tasks` table to SQLite
3. ⏳ Wire heartbeat to scan tasks (move from idle-loop to task-loop)
4. ⏳ Add task queue UI (create, list, view)
5. ⏳ Decomposition engine → planner subtask proposal
6. ⏳ Human approval gate → UI for plan review
7. ⏳ Worker pool → spawn first agent (terminal subprocess capture)

---

*Last updated: 2026-05-05 09:40 AEST*
*Based on: OpenAI Symphony SPEC.md v1, Hermes Kanban Orchestrator skill, Hermes Kanban Worker skill*
