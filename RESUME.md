# ThumbTack — Session Resume

**Project:** ThumbTack — Multi-agent AI orchestrator  
**Repo:** https://github.com/johncolling/thumbtack  
**Port:** 3456 (http://10.0.0.53:3456)  
**Status:** Phase 2 COMPLETE — Task Queue + Human Approval Gate live

## Current State
- Phase 1: System Console + Heartbeat — DONE ✅
- Phase 2: Task Queue + Human Approval Gate — DONE ✅
- Phase 3: Agent Worker Pool (spawn real agents) — NEXT ⏳

## What Was Done Last Session
- Migrated `tasks` table to Phase 2 schema (title, desc, priority, parent_task_id, planned_at, approved_at)
- Added task API: create, get, list, decompose, approve, reject, update, delete
- Added subtask creation via `POST /api/tasks/{id}/decompose` with subtasks array
- Added human approval gate: `POST /api/tasks/{id}/approve`
- Heartbeat now scans pending/queued/running separately and logs counts
- Database.py unified with canonical `init_db()` and new task helpers
- Updated `app.js` Task Queue UI with Decompose/Approve/Reject buttons
- All endpoints verified live against running server
- Committed and pushed to GitHub (master → b0f57f0)

## Next Action (when we resume)
Start Phase 3: Agent Worker Pool
- Spawn actual coding agents (claude-code, codex) as subprocesses
- Each agent gets isolated per-task git workspace
- Stream output back to dashboard
- Mark subtask done/failed on completion
- Reconcile running agents every heartbeat tick

## Files to Know
- `main.py` — FastAPI server with all routes
- `database.py` — SQLite schema + helpers
- `models.py` — Pydantic schemas
- `static/app.js` — frontend logic
- `templates/index.html` — main UI
- `ROADMAP.md` — full roadmap
