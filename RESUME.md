# RESUME.md — ThumbTack Orchestrator Session
## Session: 2026-05-05 Morning

### Current State
- **Project**: ThumbTack (~/github/johncolling/thumbtack)
- **Server**: Running on port 3456 via systemd user service
- **HEAD**: `d884046` — feat(orchestrator): Phase 1 heartbeat + system console

### What Was Just Built (Phase 1: Skeleton & Heartbeat)

#### Database
- `agent_log` table: timestamp, level, message, task_id, agent_id, project_id
- Helper functions: `add_agent_log()`, `get_agent_logs()`, `get_recent_agent_logs()`

#### Backend
- `_orchestrator_heartbeat()` — asyncio background loop, wakes every 15 min
- Scans `tasks` table for pending/running work
- Logs `AGENT_WAKE` → `AGENT_SCAN` → `AGENT_IDLE` or `AGENT_TASK_FOUND`
- FastAPI `lifespan` manager — starts heartbeat on app boot, cancels on shutdown
- `/api/orchestrator/status` — returns current status, last wake, tick count, active tasks
- `/api/agent-log` — returns last N log entries with filtering by level/project

#### Frontend
- System Console panel: fixed bottom of screen, collapsible
- Status dot with states: idle (grey), scanning (yellow), running (orange), error (red)
- Polling every 5s for logs + status
- Color-coded log levels with animations

#### Roadmap
- `ROADMAP.md` created with full 4-phase vision:
  - Phase 1: Skeleton & Heartbeat (DONE)
  - Phase 2: Human-Driven Pipeline
  - Phase 3: Autonomous Delegation
  - Phase 4: True Autonomy

### Architecture Vision (Confirmed)
ThumbTack is the orchestrator. Hermes is just the dev tool for building it.
- Persistent FastAPI server with heartbeat
- SQLite task queue
- Specialist agent workers spawned on-demand (Claude Code, Codex, etc.)
- Human gives one high-level goal → ThumbTack plans → John approves → runs autonomously
- Human reviews completed work in batches

### Next Tasks (from Things to Do.md)
1. Test the heartbeat loop — verify it fires and logs appear in System Console
2. Restart uvicorn to load the lifespan manager
3. Phase 2: Human-driven pipeline (task creation → decomposition → approval → execution)
4. External API for outside service triggers
5. Token visibility gauge in UI

### Files Modified This Session
- `ROADMAP.md` (new)
- `database.py` (agent_log table + helpers)
- `main.py` (heartbeat loop + lifespan + endpoints)
- `templates/index.html` (System Console panel)

### Environment
- John: Bundamba, Queensland, Australia
- Server IP: 10.0.0.53:3456
- Model: kimi-k2.6 (262k context)
