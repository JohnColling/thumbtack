# ThumbTack — Resume Point

> Last updated: 2026-05-04 22:10 AEST
> Head commit: `3859c7f` (pushed to github.com/johncolling/thumbtack)
>
> Screenshots in README:
> - `thumbtack-homepage.png` — Dashboard / welcome screen (no project selected)
> - `thumbtack-agents-tab.png` — Agents tab with 6 agent spawn cards
> - `thumbtack-git-tab.png` — Git tab with status, commit history, remote linking
> - `thumbtack-settings.png` — Settings panel with GitHub credentials (username, email, token, branch)

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
- **Subtitle: "Multi-agent orchestration"** — Replaced "Agent Orchestrator" everywhere (HTML title, README, code headers)

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
- **Log endpoint** — `GET /api/projects/{pid}/git/log` → returns structured commit history (hash, short_hash, author, email, date, message) via `git log --oneline --format=fuller --numstat`
- **UI features**:
  - Branch badge + clean/modified indicator
  - File list grouped by status (Staged / Modified / Untracked) with color dots
  - Click-to-expand per-file diff viewer
  - "Init Repo" button when no `.git` exists
  - Commit message input + "Commit" button
  - Manual refresh
  - **Commit History panel** — Visual commit graph with orange dots, short hash badges, author, human-readable dates
  - **Settings panel** — Username, email, token (masked as `••••••••` when saved), remote URL, branch selector. Token is preserved in DB when editing other fields.
- **SPA catch-all route** — `@app.get("/{path:path}")` redirects any unknown URL back to `/` so client-side routing works

### 3D Rotary Navigation Dial (NEW — this session)
- **Circular 3D toggle button** in sidebar footer — press in to open, press again to confirm
- **Orange gradient** with inset shadows, rotates icon 45° when depressed
- **Mouse-driven rotation** — angular velocity calculated from mouse movement around dial center
- **Smooth damping** — 12% lerp per frame via `requestAnimationFrame`
- **Two segments**: Tasks (⚡) and Terminals (💻) at 180° apart
- **Indicator pointer** at top with pulsing orange glow highlights active selection
- **Gentle idle drift** when mouse is still (auto-reverses direction)
- **Labels counter-rotate** to stay upright as dial spins
- **Click backdrop** to dismiss without navigating
- **Scalable** — `DIAL_OPTIONS` array supports 8+ future segments
- **Placeholder pages** at `/tasks` and `/terminals` with sidebar + branded layout

---

## What's Broken / Still Rough ❌

| Issue | Details |
|-------|---------|
| **Logo glass polish** | Still needs iOS candy / Aero glass effect on the two-agent sidebar icon |
| **Task queue polish** | No status indicators, timestamps, or per-task output storage yet |
| **Comparison mode** | Side-by-side diff panels work but need polish (syntax highlighting, line numbers) |
| **Mobile responsive** | Sidebar doesn't collapse on small screens |
| **MCP integration** | Tool registry not yet built |
| **Authentication** | No user accounts or session management |

---

## Critical Technical Details

| Detail | Value |
|--------|-------|
| **Repo** | `github.com/johncolling/thumbtack` |
| **Port** | `3456` |
| **Server** | `uvicorn main:app --host 0.0.0.0 --port 3456` |
| **Static** | `app.mount("/static", StaticFiles(directory="static"), name="static")` |
| **Templates** | `Jinja2Templates(directory="templates")` |
| **DB** | `sqlite3.connect("thumbtack.db")` |
| **Theme toggle** | `#themeToggle` sidebar switch — toggles `light-mode` class on `<html>`, persists to `localStorage.theme` |
| **Accent color** | `#ff7f00` (orange). Light mode uses `#e56900` for contrast. |
| **Empty-state IDs** | Two `#emptyState` elements exist — one in `#main`, one in `.main-content`. JS updates both. |
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
8. **systemd restart loops** — `Restart=always` causes crash loops during live code edits. Use `Restart=on-failure` instead.
9. **Token masking** — Token field shows `••••••••` when saved. Frontend detects dots and excludes token from POST to prevent overwriting real token with dot characters.
10. **SPA routing** — Any unknown URL hits `@app.get("/{path:path}")` which redirects to `/`. This prevents `{"detail":"Not Found"}` on browser refresh at `/project/1`.

---

## Next Session Priority Pick

When resuming, the user likely wants **ONE** of these:

1. **Logo glass polish** — iOS candy / Aero glass effect on sidebar icon
2. **Task queue polish** — Status indicators, per-task output, timestamps
3. **Comparison mode polish** — Side-by-side output panels, diff highlighting
4. **Mobile responsive** — Collapsible sidebar for smaller screens
5. **MCP integration** — Tool registry and agent tool-calling

**Ask the user which to prioritize.** Don't just start coding — confirm the direction first.
