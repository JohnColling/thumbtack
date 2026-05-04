---
yaml front matter:
  title: "RESUME.md"
  purpose: "Session restart context file"
  auto_load: true
  load_priority: "first"
  last_checkpoint: "2026-05-04 22:44:24 AEST"
---

> ⚠️ **CRITICAL: READ THIS FILE FIRST ON EVERY SESSION START.**  
> This file is the canonical wake-up state. If this is a new session, do not proceed without reading this file in full.

# Session Resume — AI Memory

**Last updated:** 2026-05-04 22:44 AEST by session autosave  
**Location:** Bundamba, Queensland, Australia  
**User:** John (two kids: Poppy, Kip)  
**Session context hibernation cycle:** In discussion — SOUL.md auto-resume directive now proposed

---

## What we were doing BEFORE this session

- **ThumbTack project** (`~/github/johncolling/thumbtack`, port 3456). FastAPI + Jinja2 SPA + SQLite + asyncio subprocesses.
- **Systemd service** for auto-restart on crash (`Restart=on-failure`, NOT always).
- **Context preservation architecture**
  - Cronjob `thumbtack-autosave` (ID `de57da2a3285`) — runs every 5 min, commits/pushes live code changes to GitHub.
  - Obsidian vault `Auto-Snapshots.md` — cronjob writes repo snapshot every 5 min.
  - Hermes memory — stable user profile (John, Poppy, Kip, Bundamba, 10.0.0.53, persona R2-D2 lightly).

## What we were doing THIS session (up to last checkpoint)

- Discussing **automated context rotation** — a cron or protocol that injects `/new` near the context ceiling, so I hibernate (save state to disk), flush memory, and resume from `RESUME.md` on wake.
- **Concept**: Like OS hibernation — serialize all working state to disk, reboot (/new), restore from disk. Gives infinite effective context.
- **Current barrier**: A Hermes cronjob cannot directly inject `/new` into your active chat client. It can only prepare the save state.
- **Potential workaround**: Make `SOUL.md` or startup instructions so aggressive that I *always* read `RESUME.md` before asking what to do. That way when you `/new` and say nothing, I auto-resume.
- **Action this session**: Saving checkpoint (this file), committing to GitHub, updating Things to Do.md.

---

## Active Decisions / Open Threads

| # | Topic | Status | Blocker |
|---|-------|--------|---------|
| 1 | Automated context rotation (`/new` on schedule) | 🔴 DESIGNING | Needs client-side trigger or gateway bot injection |
| 2 | API for external services to trigger ThumbTack | 🟡 QUEUED | Needs design — webhooks? FastAPI endpoint? |
| 3 | Task queue polish (status, output, timestamps) | 🟡 TODO | — |
| 4 | Comparison mode polish (syntax highlight, line numbers) | 🟡 TODO | — |
| 5 | Mobile responsive sidebar | 🟡 TODO | — |
| 6 | MCP integration | 🟡 TODO | — |

---

## Technical Stack (for quick recall)

| Layer | Detail |
|-------|--------|
| Backend | FastAPI 0.136.1, uvicorn, Starlette 1.0.0 |
| Frontend | Jinja2 SPA, vanilla JS, CSS variables (`light-mode` class on `<html>`) |
| DB | sqlite3 (`thumbtack.db`) — tables: projects, agents, tasks, comparisons, git_settings |
| Agents | asyncio subprocess: claude, codex, opencode, openclaw, aider, custom |
| WS | `/ws` broadcasts `{stream, data}` |
| SPA route | Catch-all `@app.get("/{path:path}")` redirects unknown paths to `/` |
| Theme | Dark `#0f1115`, light white, accent `#ff7f00`, neon sidebar glow |
| Git | Remote linking with masked token field |

---

## Critical Pitfalls

1. **TemplateResponse signature changed** in FastAPI 0.136+ → use positional `templates.TemplateResponse(request, "index.html")`, not the old dict format. Clear cache: `templates.env.cache.clear()`.
2. **Two `#emptyState` elements** in DOM — `getElementById` returns first match; use class selectors.
3. **Port 3456 zombie detection**: `lsof -i :3456` or `ps aux | grep uvicorn`.
4. **Python cache**: `find . -type d -name __pycache__ -exec rm -rf {} +` after `.py` edits.
5. **systemd**: `Restart=on-failure` only.
6. **Token masking**: Settings token shows `••••••••`. Frontend detects dots and excludes token from POST payload to prevent overwriting real token with dots.
7. **Name**: ThumbTack (capital T in Tack).

---

## Context-Rotation Protocol (Proposed)

When context nears ceiling (~70-80% or time expires):
1. Output `[CONTEXT_CHECKPOINT_REQUIRED]` with summary
2. Auto-save: dump all active task state → `RESUME.md`
3. Wait for user `/new`
4. On wake, STARTUP INSTRUCTIONS force read `RESUME.md` before anything else
5. Resume as if no gap occurred

This is NOT yet implemented. Currently manual `/new` + manual read.

---

## Files to read on next session

1. **This file** (`RESUME.md`) — ALWAYS FIRST
2. **`../Things to Do.md`** — shared task list
3. `git status` — check what changed on disk vs repo
4. `Auto-Snapshots.md` in Obsidian — for 5-min granularity

---

> **If John says nothing after `/new`**, startup instructions should assume "resume from last checkpoint" and pick the top open thread without asking.
