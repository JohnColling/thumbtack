# Thumbtack — Resume Point

> Last updated: 2026-05-04, evening session
> Head commit: `f1a7946` (pushed to github.com/johncolling/thumbtack)

---

## How to Start

```bash
cd ~/github/johncolling/thumbtack
# If env changed:
python -m uvicorn main:app --host 0.0.0.0 --port 3456
# Or via systemd: systemctl --user restart thumbtack
```

Server runs at: `http://10.0.0.53:3456`

---

## What's Working ✅

### UI & Branding
- **Dark/light theme toggle** — Sidebar switch, persists to `localStorage`, CSS vars swap between dark `#0f1115` and light `#ffffff` palettes
- **Orange accent (`#ff7f00`)** — All CTA buttons, active tabs, links. Light mode uses `#e56900` (darker orange for contrast)
- **Ghost watermark logo** — Two-agent SVG icon, orange `#ff7f00` at 8% opacity, fills empty-state area when no project selected. Responsive sizing via `min(127%, 104vh)` — auto-scales to viewport
- **Neon sidebar divider** — 1px `#ffaa44` core line with `box-shadow` glow layers (1px → 5px spread), creating a bright neon tube effect on the edge between sidebar and main content. No ambient pseudo-layer — pure focused glow.
- **Two-agent icon (top-left)** — Orange `#ff7f00` base, white specular arc. Functional but still waiting for final glass-candy polish
- **Conditional empty-state CTA** — "Create your first project" when 0 projects exist; "Add another project" when ≥1 exist

### Backend
- **FastAPI** runs clean on port 3456
- **SQLite DB** (`thumbtack.db`) — projects, agents, tasks, comparisons tables
- **Project creation** — Bare name auto-nests under `~/thumbtack_projects/<name>`. Absolute paths used as-is.
- **Directory auto-creation** — `os.makedirs(..., exist_ok=True)` on project create
- **WebSocket streaming** — `ws://10.0.0.53:3456/ws`, broadcasts `{stream, data}` format

### File Browser
- **Per-project file tree** — Recursive tree view with expand/collapse, file icons
- **Breadcrumb navigation** — Click any segment to navigate up
- **File preview** — Text files rendered with syntax-highlighted line numbers
- **Folder creation** — "New Folder" button in any directory

### Agent Spawning
- **6 agent types**: claude, codex, opencode, openclaw, aider, custom
- **Working directory** set to project path on spawn
- **WebSocket output** streams live to connected clients

### Task Queue
- **Add / delete / run / run-all / clear-done**
- **Per-task run endpoint** — `POST /api/tasks/{id}/run` dispatches to active agent

### Comparison Mode
- **Backend endpoint** — `POST /api/comparison` spawns two agents side-by-side
- **Frontend** — Comparison tab with agent selectors and run button
- **WebSocket format fix** — `sendComparisonCommand` now sends proper `{type, name, prompt, comparison_mode}`

### Git Integration (NEW — this session)
- **Git tab** in project detail view — 4th tab alongside Agents, Files, Tasks, Comparison
- **Status endpoint** — `GET /api/projects/{pid}/git/status` → branch, ahead/behind, clean/dirty, file counts (staged / modified / untracked)
- **Diff endpoint** — `GET /api/projects/{pid}/git/diff?filepath=...` → unified diff with per-line +/-/header parsing
- **Init endpoint** — `POST /api/projects/{pid}/git/init` → `git init` in project directory
- **Commit endpoint** — `POST /api/projects/{pid}/git/commit` with `{"message":"..."}` → `git add -A && git commit -m <msg>`
- **UI features**:
  - Branch badge + clean/modified indicator
  - File list grouped by status (Staged / Modified / Untracked) with color dots
  - Click-to-expand per-file diff viewer
  - "Init Repo" button when no `.git` exists
  - Commit message input + "Commit" button
  - Manual refresh

---

## Filesystem Structure

```
/home/administrator/
├── thumbtack_projects/          ← master parent folder
│   └── <project-name>/          ← auto-created on "Create Project"
└── github/johncolling/thumbtack/ ← repo
    ├── main.py                  ← FastAPI app (all endpoints + WebSocket)
    ├── static/app.js            ← SPA frontend logic
    ├── templates/
    │   └── index.html           ← Single-page app (sidebar + main area + all tabs)
    ├── agent.py                 ← (legacy/orphaned) early agent spawn logic
    ├── model.py                 ← (legacy/orphaned) early Pydantic models
    ├── requirements.txt         ← FastAPI, Jinja2, uvicorn, websockets
    └── thumbtack.db             ← SQLite database
```

---

## What's Pending / Broken ⚠️

### 1. Icon Glass Effect (POLISH — not blocking)
The top-left logo needs iOS candy / Windows Aero glass — thick translucent dome with bright white specular highlight. Current version is functional (orange base + white arc) but doesn't quite have that glossy depth.

**Files:** `templates/index.html` — CSS under `/* ── logo ── */`, `.gloss`, `.gleam`, `.rim`

### 2. Auto-Commit Message Suggestions (ENHANCEMENT)
Currently requires manual commit message input. Could add an "Auto-generate message" button that creates a summary like `WIP — 3 files changed`.

### 3. Git Log / History (NOT BUILT)
Only current status, diff, and commit are implemented. No `git log` viewing yet.

### 4. MCP Integration (NOT BUILT)
No MCP tool registry or calling logic.

### 5. Authentication (NOT BUILT)
Any device on the LAN can currently spawn agents at `10.0.0.53:3456`.

### 6. Mobile Layout (NOT BUILT)
Sidebar is fixed 280px, content area is desktop-sized. Need responsive breakpoints for sidebar collapse.

### 7. Comparison Mode Frontend Polish
Tab exists and backend endpoint works, but the side-by-side output display could be richer (e.g., separate panels per agent, diff highlighting).

### 8. Task Queue Frontend Polish
Task list renders but could use inline status indicators (running / done / failed), timestamps, and per-task output viewing.

---

## Key Design Decisions to Preserve

| Decision | Detail |
|----------|--------|
| **Accent color** | `#ff7f00` (pure orange). Light mode: `#e56900` |
| **Dark bg** | `#0f1115` (near-black, slightly blue-tinted) |
| **Light bg** | `#ffffff` (pure white) |
| **Sidebar dark** | `#161b22` (GitHub-style dark gray) |
| **Font** | Inter (Google Fonts) |
| **Icon concept** | Two small figures (T-shapes with circle heads) holding hands — represents multi-agent collaboration |
| **Project paths** | Auto-nest bare names under `~/thumbtack_projects/`. Absolute paths preserved as-is. Tilde `~` expanded. |
| **Name** | **ThumbTack** (not Thumbtack) — capital T in Tack |
| **Neon border** | 1px core line with `box-shadow` glow. No `filter: drop-shadow` (renders poorly in some browsers). Spread values: 0px, 1px, 2px, 3px, 5px |

---

## Known Pitfalls

1. **Context expiry risk** — This project MUST survive session ends. Always verify code on disk after edits. The repo is the source of truth.
2. **TemplateResponse bug** — If upgrading FastAPI: use `templates.TemplateResponse(request, "index.html")` NOT the old dict-style. Also `templates.env.cache.clear()` if templates are stale.
3. **Port 3456 conflict** — If the server won't start, check for old uvicorn processes with `lsof -i :3456` or `ps aux | grep uvicorn`.
4. **Python cache** — After patching `.py` files, clear `__pycache__` with `find . -type d -name __pycache__ -exec rm -rf {} +` if changes don't seem to take effect.
5. **Static files** — `app.js` serves from `/static/app.js`. If the browser gets 404, check `main.py` has `app.mount("/static", ...)`.
6. **WebSocket format** — Backend broadcasts must use `{stream, data}` format. Older format `{type, line}` will break frontend log parsing.
7. **Two #emptyState elements** — One in `#main`, one in `.main-content`. `getElementById` returns the first. Updates target both via class selectors where needed.

---

## Next Session Priority Pick

When resuming, the user likely wants **ONE** of these:

1. **Logo glass polish** — iOS candy / Aero glass effect on sidebar icon
2. **Git log / history** — View past commits in the Git tab
3. **Task queue polish** — Status indicators, per-task output, timestamps
4. **Comparison mode polish** — Side-by-side output panels, diff highlighting
5. **Mobile responsive** — Collapsible sidebar for smaller screens
6. **MCP integration** — Tool registry and agent tool-calling

**Ask the user which to prioritize.** Don't just start coding — confirm the direction first.
