# Things to Do

> Dump anything here — ideas, fixes, tasks, reminders. I'll work through them session by session.
> **To add:** Just dictate or paste. One line per item is fine. I can clean up formatting.
> **To update:** Mark items `in progress`, `done`, or `parked`. I'll update status as I go.

---

## 🟡 Active / Next Up

*(Items I'm currently working on or will pick up next)*

- [ ] External API for ThumbTack — Design endpoints so outside services/programs can trigger agents, tasks, or events inside the application (REST + WebSocket? Simple webhook? Needs scoping)

---

## 🔴 Urgent (Do ASAP)

- [x] ~~Design auto context-rotation system~~ — **DONE (semi-auto protocol live)**. SOUL.md auto-resume confirmed. Semi-auto flow: I emit `[CONTEXT_CHECKPOINT_REQUIRED]` → John `/new`s → new session auto-loads RESUME.md. True auto-`/new` (tmux script or gateway hook) still to build.
- [ ] Investigate external API for ThumbTack — Allow outside services/programs to trigger agents, tasks, or events inside the application

---

## 🟢 Todo (Queued)

- [ ] Logo glass polish (iOS candy / Aero effect)
- [ ] Task queue / comparison mode polish
- [ ] MCP integration (tool registry)
- [ ] Auth / login wall
- [ ] Mobile responsive layout

---

## 🔵 Ideas / Someday Maybe

- [ ] Investigate Heartbeat Implementation — Cronjob that wakes agent every 5 min to save live context + push to GitHub. Agent itself does the save, not the cronjob. ✅ DONE — see job `heartbeat-poke` (`2fad6e35cf49`).
- [ ] True auto-`/new` automation — Local tmux script or gateway hook that detects `[CONTEXT_CHECKPOINT_REQUIRED]` and physically sends `/new` into the chat thread, making the hibernation cycle fully hands-off.

---

## ✅ Recently Done

*(I'll move completed items here so you have a record)*

- [x] *Created this running task list file* — 2026-05-04
- [x] *Implemented heartbeat cronjob* — 2026-05-04
- [x] *Confirmed SOUL.md auto-resume directive* — 2026-05-04 (verified in `run_agent.py:4882` that SOUL.md is Layer 1 of system prompt)
- [x] *Saved session checkpoint to RESUME.md* — 2026-05-04

---

## How John & R2 Use This File

1. **You dictate** → I append to the right section.
2. **I pick the top item** from 🟡 Active or 🔴 Urgent and work it.
3. **I mark it done** and move it to ✅ Recently Done.
4. **If something's blocked**, I mark it `parked — reason` and move to 🔵 Ideas.
5. **No pressure** — if you just want to brain-dump, dump. I'll organise.
