---
yaml front matter:
  title: "RESUME.md"
  purpose: "Session restart context file"
  auto_load: true
  load_priority: "first"
  last_checkpoint: "2026-05-04 23:31:25 AEST"
---

> ⚠️ **CRITICAL: READ THIS FILE FIRST ON EVERY SESSION START.**  
> This file is the canonical wake-up state. If this is a new session, do not proceed without reading this file in full.

# Session Resume — AI Memory

**Last updated:** 2026-05-04 23:31 AEST by session autosave  
**Location:** Bundamba, Queensland, Australia  
**User:** John (two kids: Poppy, Kip)  
**Session context hibernation cycle:** ACTIVE — SOUL.md auto-resume directive confirmed working

---

## 🚀 ACTIVE PROJECT: ThumbTack Multi-Agent Orchestrator

- **Repo:** https://github.com/johncolling/thumbtack (public)  
- **Local path:** `~/github/johncolling/thumbtack`  
- **Server:** http://10.0.0.53:3456 (systemd user service)  
- **Git branch:** `master`, clean (HEAD: `9d43a17`)  
- **Tech stack:** FastAPI + Jinja2 + SQLite + Tailwind CSS + asyncio subprocesses

**Just done in this session:**
- Investigated Hermes source (`run_agent.py:4861+`) to confirm SOUL.md is the VERY FIRST layer injected into the system prompt at session start
- Confirmed SOUL.md already contains hard directive to auto-read RESUME.md and Things to Do.md on first message of every new session
- Discussed automating `/new` — found it is a client-side UI command; Hermes cronjobs run in isolated sessions and cannot inject commands into the current chat thread
- Identified that true auto-`/new` automation requires a local script (tmux send-keys) or gateway-level hook, not a Hermes cronjob alone
- Agreed on **semi-automatic protocol** for now: when context pressure nears 70–80%, I emit `[CONTEXT_CHECKPOINT_REQUIRED]` → John manually `/new`s → new session auto-loads this file via SOUL.md directive
- Recorded new task: Add external API to ThumbTack (allow outside services/programs to trigger agents, tasks, or events inside the application)

**New tasks on running list:**
1. 🔴 Design auto context-rotation system — In progress. SOUL.md resume confirmed. Need local auto-`/new` trigger mechanism (tmux script or gateway hook).
2. 🔴 Investigate external API for ThumbTack — Allow outside services/programs to trigger agents, tasks, or events inside the application.

**Still on the backlog:**
- Logo glass polish (iOS candy / Aero effect)
- Task queue / comparison mode polish
- MCP integration (tool registry)
- Auth / login wall
- Mobile responsive layout

---

## ⚙️ CRITICAL ENVIRONMENT FACTS

| Fact | Value |
|---|---|
| John's local IP | **10.0.0.53** (not localhost; never use 127.0.0.1) |
| ThumbTack port | 3456 |
| Vault root | `/home/administrator/Obsidian Vault/` |
| Running tasks | `Things to Do.md` at vault root |
| FastAPI template bug | Use `templates.TemplateResponse(request, "index.html")` (new positional signature); clear cache with `templates.env.cache.clear()` |
| systemd restart policy | `Restart=on-failure` (never `always`) |
| Token masking | Frontend sends `"••••••••"` as sentinel; server detects and skips overwrite |
| Hermes SOUL.md path | `~/.hermes/SOUL.md` — loaded as Layer 1 of system prompt every session |
| Hermes memory files | `~/.hermes/memories/MEMORY.md` + `~/.hermes/memories/USER.md` |

---

## 🔄 SESSION HIBERNATION PROTOCOL (ACTIVE — TESTING)

**Goal:** Automated context-window hibernation so the agent never hits 100% context, giving effectively infinite working memory.

**Confirmed architecture:**
- `SOUL.md` is the first layer of the system prompt (verified in `run_agent.py:4882`). It is injected before memory, skills, tool guidance, and everything else.
- The hard directive inside `SOUL.md` to read `RESUME.md` and `Things to Do.md` on every new session is already active and effective.
- A new session (triggered by `/new`) will automatically load state from disk before rendering its first reply.

**Current flow:**
1. **Save** — autosave cron already saves state every 5 min (memory, Obsidian, GitHub)
2. **Alert** — when context pressure builds, I emit `[CONTEXT_CHECKPOINT_REQUIRED] + summary`
3. **Reset** — John types `/new` (manual for now)
4. **Resume** — new session reads this file automatically via SOUL.md directive → state restored

**Automation gap:**
- A Hermes `cronjob` runs in an isolated session — it **cannot** inject `/new` into your live chat thread
- `/new` is a **client-side UI command** (parsed by Telegram/Discord/terminal/prompt_toolkit)
- **Potential local fix:** A bash cronjob that knows your tmux session name can run `tmux send-keys -t hermes "/new" Enter`
- **Potential gateway fix:** A custom gateway hook or a second bot that sends `/new` into the channel
- **Decision:** Keep semi-auto for now. When it starts working well, we can script the final mile.

---

## 📋 SERVICES ON r2-d2 (10.0.0.53)

| Service | Port | Status |
|---|---|---|
| Thumbtack | 3456 | systemd user, active focus |
| Horse Racing Data Vault | 80 | systemd user, stable |
| CloudCLI | 3001 | npx process, stable |
| Codeg | 3080 | systemd user, needs desktop token |
| Ollama | 11434 | standalone, local LLM |
| SSH | 22 | system |

---

## 🧠 HERMES STATE

- **Cronjob:** `de57da2a3285` (`thumbtack-autosave`, every 5 min)
- **Pre-run script:** `~/.hermes/scripts/thumbtack-cron-preamble.py`
- **Memory targets:** `memory` + Obsidian `Session Snapshots/` + GitHub
- **Persona file:** `~/.hermes/SOUL.md` → Layer 1 of every system prompt; contains hard directive to read RESUME.md
- **User profile:** John, Bundamba QLD, two kids (Poppy and Kip), prefers R2-D2 persona lightly (drop beep-boop in execution mode)

---

## ✅ FIRST ACTIONS ON NEW SESSION

1. **Read this file fully** — you're reading it now ✓
2. **Read `Things to Do.md`** in vault root — pick the top open item
3. **Check Thumbtack status** — `systemctl --user status thumbtack`
4. **Check last autosave** — `cd ~/github/johncolling/thumbtack && git log --oneline -3`
5. **Ask John** what he wants to work on next

---

*This file is written at the end of every significant session. If the timestamp is fresh, load state from here. If stale (> 15 minutes), treat with caution and ask for confirmation.*
