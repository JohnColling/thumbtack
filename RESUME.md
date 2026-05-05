# ThumbTack Orchestrator — Session Resume

## Current State
**Phase:** 3 (Agent Worker Pool) — ~90% complete
**Branch:** master (pushed to GitHub)
**Server:** Running on port 3456
**Database:** thumbtack.db (SQLite)

## What's Working
- Worker pool dispatches tasks, spawns agents with subprocess isolation
- Task outputs captured to task_outputs table
- Status lifecycle: queued → running → done/failed
- WebSocket streaming for live output
- Pause/resume/stop controls via API

## WIP: Task Decomposition Engine
- `task_decomposer.py` created (222 lines)
- Connects to localhost:11434 Ollama for LLM planning
- **BUG:** LLM calls timeout at ~60s despite keep_alive=-1 and timeout=180
- `kimi-k2.6:cloud` model via Ollama is not responding reliably to API calls
- **NOTE:** `glm-4.7-flash` on Ollama is extremely slow (minutes) for decomposition
- **Next:** Fix LLM call mechanism — different endpoint/port, batch approach, or template-based decomposition
- Endpoints added: POST /api/tasks/{tid}/auto-plan (not yet fully tested)
- UI: "Auto Plan" modal added in app.js

## Known Issues
1. `claude -p` agent on worker_pool.py line 51 passes task data via env vars (no stdin prompt) — causes exit code 1
2. Task outputs order by `created_at` (second precision) — lines within same second may be out of order
3. LLM decomposition timeout — needs robust retry/fallback (template-based) + stream-based approach

## Session Interrupted
- Mid-debug on `task_decomposer.py` LLM timeout issue
- Context hibernation triggered by user

## Next Action
Resolve LLM timeout in `task_decomposer.py` and test end-to-end auto-decomposition flow.
