# ThumbTack — Master Roadmap
## Vision: Autonomous Multi-Agent Orchestration Platform

ThumbTack is a persistent, task-based orchestrator. It wakes on interval, scans its task queue, delegates work to specialist agents (Claude Code, Codex, OpenCode, etc.), and reports results. The human (John) provides high-level goals, approves plans once, and reviews completed work in batches.

---

## Phase 1: Skeleton & Heartbeat (CURRENT)
**Goal:** Visible proof-of-life. The app shows it's alive, scanning, and idle or working.

| Item | Status |
|------|--------|
| `agent_log` table in SQLite | 🔨 Building |
| Background asyncio heartbeat loop | 🔨 Building |
| `/api/agent-log` endpoint | 🔨 Building |
| System Console panel in UI | 🔨 Building |
| Task queue schema (`tasks` extended) | 🔨 Building |

**Heartbeat behaviour:**
- Wakes every 15 minutes
- Logs `AGENT_WAKE` → `SCAN_QUEUE` → `IDLE` (if empty) or `TASK_START` (if work found)
- UI shows scrolling terminal-style feed of these events

---

## Phase 2: Human-Driven Pipeline
**Goal:** John creates a task → I decompose into subtasks → write to queue → show plan → John approves → manual trigger each subtask.

| Item | Status |
|------|--------|
| Task creation API + UI | ⏳ |
| Plan decomposition (LLM call) | ⏳ |
| Subtask queue with dependencies | ⏳ |
| Approval gate (human-in-the-loop) | ⏳ |
| Manual subtask trigger | ⏳ |

---

## Phase 3: Autonomous Delegation
**Goal:** ThumbTack decomposes, plans, and delegates without per-step human input.

| Item | Status |
|------|--------|
| LLM-based task decomposition engine | ⏳ |
| Agent worker pool (spawn Claude Code/Codex) | ⏳ |
| Parallel execution with isolation | ⏳ |
| Output capture & streaming | ⏳ |
| Retry & failure handling | ⏳ |
| Task state machine (kanban) | ⏳ |

**Worker isolation requirements:**
- Each agent gets its own process / tmux session
- Output streamed back to dashboard in real-time
- Git workspace isolation (branch-per-agent or clone-per-task)
- Credential management per agent context
- Lifecycle: spawn → monitor → capture → kill → report

---

## Phase 4: True Autonomy
**Goal:** One high-level goal → plan → approve once → run for hours/days → report back.

| Item | Status |
|------|--------|
| Autonomous planning without human decomposition | ⏳ |
| Long-running execution (survives disconnects) | ⏳ |
| Progress reporting at intervals | ⏳ |
| Blocker detection → human escalation | ⏳ |
| Self-healing (retry failed subtasks) | ⏳ |

---

## Known Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite for queue** | Lightweight, zero config, single-node. Migrate to Postgres only if multi-node. |
| **Asyncio background loop** | Already inside FastAPI. No need for Celery/RabbitMQ yet. |
| **Agent subprocess spawning** | Uses existing `AgentProcess`/`AgentManager` pattern. Each agent = CLI process. |
| **No Hermes dependency** | ThumbTack is standalone. Hermes is John's dev tool, not the runtime. |
| **WebSocket/SSE for real-time** | Dashboard updates without polling. Fallback to polling acceptable. |
| **Token estimation in-app** | `tiktoken` or Kimi tokenizer runs inside ThumbTack to estimate LLM payload sizes. |

---

## External API Vision (from todo)
Allow outside services to trigger tasks inside ThumbTack:
- `POST /api/external/trigger` with auth token
- Webhook support for GitHub PRs, CI events, scheduled triggers
- Response: task ID + estimated start time

---

## Token Visibility (from todo)
Build a fuel gauge in the UI:
- Estimate tokens per task before sending to LLM
- Show running total for active agents
- Warn at 80% of model context limit
- Use `tiktoken` or platform-specific tokenizer

---

*Last updated: 2026-05-05*
