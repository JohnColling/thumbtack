# RESUME — Session Checkpoint

> **CRITICAL: This file is read on EVERY new session start. Do not skip.**
> **Last updated:** 2026-05-04 ~22:48 AEST  
> **Location:** Bundamba, Queensland, Australia  
> **User:** John (two kids: Poppy and Kip)

---

## 🚀 ACTIVE PROJECT: ThumbTack Multi-Agent Orchestrator

- **Repo:** `https://github.com/johncolling/thumbtack`  
- **Local path:** `~/github/johncolling/thumbtack`  
- **Server:** `http://10.0.0.53:3456`  
- **Git branch:** `master`  
- **HEAD commit:** `fd32995` — "docs: update RESUME.md with context-rotation concept and current session state"  
- **Tech stack:** FastAPI + Jinja2 + SQLite + Tailwind CSS + asyncio subprocesses  

**State of code:** Clean working tree. `static/app.js` has working rotary dial JS. Templates have glass logo and neon sidebar.

---

## 📋 CURRENTLY DISCUSSING / BUILDING

This session (2026-05-04 late evening):
1. **Discussed automated context-window hibernation** — save everything, `/new` reset, auto-resume from RESUME.md
2. **Verified SOUL.md auto-read protocol** — `SOUL.md` is Layer 1 of system prompt; confirmed by `run_agent.py:4882`
3. **SOUL.md already contains the SESSION RESURRECTION PROTOCOL that forces a `read_file` of this RESUME.md on every new session**
4. **Current idea:** Design a cronjob or local script that can trigger `/new` automatically every ~15 min, so context never fills. In a terminal session this would need `tmux send-keys`; in a gateway session (Discord/Telegram) it's harder because `/new` is a client command.
5. **Decision:** Semi-auto for now — I'll save proactively and emit `[CONTEXT_CHECKPOINT_REQUIRED]`; John manually `/new`s when convenient. Later we can script the final keystroke.

---

## 🔴 TOP OPEN TASKS (from Things to Do.md)

1. **External API for ThumbTack** — Design REST/WebSocket endpoints so outside services can trigger agents, tasks, or events  
   (This is 🟡 Active / Next Up)
2. **True auto-`/new` automation** — Local `tmux send-keys` script or gateway hook that detects context pressure and physically sends `/new`, making hibernation fully hands-off  
3. **Logo glass polish** (iOS candy / Aero effect)  
4. **Task queue / comparison mode polish**  
5. **MCP integration** (tool registry)  
6. **Auth / login wall**  
7. **Mobile responsive layout**

---

## ⚙️ CRITICAL ENVIRONMENT FACTS

| Fact | Value |
|---|---|
| John's local IP | **10.0.0.53** (never 127.0.0.1) |
| ThumbTack port | 3456 |
| Vault root | `/home/administrator/Obsidian Vault/` |
| Running tasks | `Things to Do.md` at vault root |
| FastAPI template bug | Use `templates.TemplateResponse(request, "index.html")` + `templates.env.cache.clear()` |
| systemd restart policy | `Restart=on-failure` only |
| Token masking | Frontend sends `"••••••••"`; server detects and skips overwrite |

---

## 🔄 CONTEXT PRESERVATION SYSTEM

| Component | Detail |
|---|---|
| Cronjob | `de57da2a3285` (`thumbtack-autosave`, every 5 min) |
| Pre-run script | `~/.hermes/scripts/thumbtack-cron-preamble.py` |
| Hermes memory | `memory` tool — 2,200 char budget |
| Obsidian snapshots | `AI Memory/Projects/ThumbTack/Auto-Snapshots.md` |
| GitHub backup | Auto-push on cron tick if dirty |
| Persona / resume | `~/.hermes/SOUL.md` → Layer 1 of system prompt |
| Canonical resume | This file (`/home/administrator/Obsidian Vault/AI Memory/RESUME.md`) |

**Current status:** Semi-automatic. Auto-save is live. Auto-`/new` is not yet built — requires either tmux scripting or gateway-level support.

---

## 📋 SERVICES ON r2-d2 (10.0.0.53)

| Service | Port | Status |
|---|---|---|
| Thumbtack | 3456 | Active focus |
| Horse Racing Data Vault | 80 | Stable |
| Codeg | 3080 | Needs desktop token |
| Ollama | 11434 | Local LLM |
| SSH | 22 | System |

---

*Read this file first. Read `Things to Do.md` second. Start working the top task unless John says otherwise.*
