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

## 🚀 ACTIVE PROJECT: ThumbTack Multi-Agent Orchestrator

- **Repo:** https://github.com/johncolling/thumbtack (public)  
- **Local path:** `~/github/johncolling/thumbtack`  
- **Server:** http://10.0.0.53:3456 (systemd user service)  
- **Git branch:** `master`, clean (HEAD: `e5d48af`)  
- **Tech stack:** FastAPI + Jinja2 + SQLite + Tailwind CSS + asyncio subprocesses

**Just done in this session:**
- Discussed automating context-window hibernation (save → `/new` → resume from RESUME.md)
- Decided SOUL.md should contain hard directive to auto-read this file on first message of new session  
- Committed updated `thumbtack/RESUME.md` to GitHub

**Still on the task list:**
- See `Things to Do.md` in Obsidian vault root for John's running task list
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

---

## 🔄 SESSION HIBERNATION PROTOCOL (IN PROGRESS)

**Goal:** Automated `/new` rotation so context never hits 100%, giving theoretical infinite memory.

**Flow:**
1. **Save** all active state → this RESUME.md + Hermes memory + Git push
2. **Inject `/new`** into chat (or local script triggers it)
3. **Wake** → new session automatically loads this file (via SOUL.md persona directive)
4. **Resume** → pick up exactly where we left off

**Blockers:**
- `/new` is a client-side UI command; a Hermes cronjob cannot directly inject it into the active chat thread
- If using gateway (Discord, Telegram), the cron can `deliver` a message, but that *adds* tokens rather than clearing them
- Local terminal/tmux: `tmux send-keys -t hermes "/new\" Enter` could script it
- True automation needs either a custom client script or Hermes gateway-level support

**Current stance:** Semi-auto for now. When context pressure builds, I emit `[CONTEXT_CHECKPOINT_REQUIRED]` and wait for John to `/new`. Then resume from this file.

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
- **Persona file:** `~/.hermes/SOUL.md` → hard directive to read this file on every new session
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
