# ThumbTack — Session Resume

**Updated:** 2026-05-05 17:23:53 AEST
**Branch:** master

## Current Status

- **Server:** Running on port 3456 (uvicorn background PID — started directly, systemd disabled during dev)
- **Phase:** Phase 2 COMPLETE (Human-Driven Pipeline)
- **Next:** Phase 3 — Agent Worker Pool (spawn real agents, isolate workspaces, stream output, mark done/failed)

## Active Artifacts

| File | Status |
|------|--------|
| `main.py` | Phase 2 task API + heartbeat restart guard |
| `database.py` | Canonical schema + all task helpers |
| `templates/index.html` | Phase 2 UI (decompose/approve/reject buttons) |
| `static/app.js` | Updated task actions |
| `test_api.sh` | API smoke tests (10/10 pass) |

## Critical Bugs Fixed This Session

1. **Systemd `fuser -k` murder loop** — `ExecStartPre` in service file was SIGKILLing the server on every restart, causing 3,273 restarts. Fixed by running uvicorn directly outside systemd during dev.
2. **Heartbeat idempotency** — Added `HEARTBEAT_STARTED` guard in lifespan to prevent duplicate heartbeat tasks on restart.
3. **Restart detection** — Lifespan checks for SYSTEM/RESTART log within 60s, logs `RESTART` instead of `SYSTEM`.

## Git Status

```
2884836 Phase 2: Add restart detection to prevent duplicate heartbeat tasks on systemd restart loops
---
 M RESUME.md
 M thumbtack.db
```

## Quick Resume Command

```bash
cd ~/github/johncolling/thumbtack
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 3456 &
```
