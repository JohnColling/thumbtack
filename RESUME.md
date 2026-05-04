# Thumbtack — Resume Point

> Last updated: 2026-05-04 evening session  
> Commit: `ba308e0` (pushed to github.com/johncolling/thumbtack)

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

### UI
- **Dark/light theme toggle** — Sidebar switch, persists to `localStorage`, CSS vars swap between dark `#0f1115` and light `#ffffff` palettes
- **Ghost watermark logo** — Two-agent SVG icon at 280×280, orange `#ff7f00` at 35% opacity, fills empty state area when no project selected
- **Icon (top-left)** — Two figures holding hands, orange `#ff7f00` base, white specular arc — still needs final glass polish
- **Responsive-ish** — Mostly desktop-focused right now

### Backend
- **FastAPI** runs clean on port 3456
- **SQLite DB** (`thumbtack.db`) — projects, agents, tasks, comparisons tables
- **Project creation** — Bare name (e.g. `demo-app`) auto-nests under `~/thumbtack_projects/<name>`. Absolute paths (`/home/administrator/...`) used as-is.
- **Directory auto-creation** — `os.makedirs(..., exist_ok=True)` on project create

### Filesystem Structure
```
/home/administrator/
├── thumbtack_projects/          ← master parent folder
│   ├── demo-app/               ← sample project with src/, tests/, docs/, etc.
│   ├── test2/                  ← user's project
│   └── test-project/           ← legacy project
└── github/johncolling/thumbtack/ ← repo
    ├── main.py
    ├── static/app.js
    ├── templates/
    │   ├── index.html          ← main SPA
    │   └── project.html        ← legacy detail page (needs rebuild)
    └── thumbtack.db
```

---

## What's Pending / Broken ⚠️

### 1. Icon Glass Effect (HIGH PRIORITY)
The top-left logo needs to look like **iOS candy glass / Windows Aero** — thick translucent dome with bright white specular highlight curving across the top, deep orange glowing from underneath.

**Current state:** Orange `#ff7f00` base gradient with a white specular arc, but the glass layers aren't quite right. Still looks slightly muddy rather than glossy.

**Reference:** Think old iOS app icons — thick beveled edge, internal glow, white curved highlight on the dome surface.

**Files to hit:** `templates/index.html` — CSS inside the `<style>` block under `/* ── logo ── */`, `.gloss`, `.gleam`, `.rim`, and the SVG face dots.

### 2. Project Detail Page (HIGH PRIORITY)
`templates/project.html` is stale — hardcoded paths, old CSS, doesn't show the actual file tree or agent status. Needs a rebuild to match the index.html dark/light theme.

**Desired:** When you click a project in the sidebar, it should show:
- File tree (per-project browsable tree view)
- Running agents + their status
- Task queue for that project
- Git status (if applicable)

**Files to hit:** `templates/project.html` — probably easier to rebuild from scratch using the index.html base + new content area.

### 3. Comparison Mode Endpoint (STUB)
`agent.py` and `model.py` exist for comparison mode, but `POST /api/comparison` in `main.py` is **unimplemented**. The idea: spawn two agents on the same task, stream results side-by-side.

### 4. Task Queue Endpoint (STUB)
DB table + models exist, but `POST /api/tasks/{id}/run` in `main.py` is **unimplemented**.

### 5. Auto-Commit / Git Integration (NOT BUILT)
No git logic in the backend. Would need:
- `git status` / `git diff` display
- Auto-generated commit message suggestion
- One-click commit button

### 6. MCP Integration (NOT BUILT)
No MCP tool registry or calling logic.

### 7. Authentication (NOT BUILT)
Any device on the LAN can currently spawn agents at `10.0.0.53:3456`.

### 8. Mobile Layout (NOT BUILT)
Sidebar is fixed-width, content area is desktop-sized. Need responsive breakpoints.

---

## Key Design Decisions to Preserve

| Decision | Detail |
|----------|--------|
| **Accent color** | `#ff7f00` (pure orange, not amber `#ffa000` or red `#ff3d00`) |
| **Dark bg** | `#0f1115` (near-black, slightly blue-tinted) |
| **Light bg** | `#ffffff` (pure white) |
| **Sidebar dark** | `#161b22` (GitHub-style dark gray) |
| **Font** | Inter (Google Fonts) |
| **Icon concept** | Two small figures (T-shapes with circle heads) holding hands — represents multi-agent collaboration |
| **Project paths** | Auto-nest bare names under `~/thumbtack_projects/`. Absolute paths preserved as-is. Tilde `~` expanded. |
| **Name** | **ThumbTack** (not Thumbtack) — capital T in Tack |

---

## Known Pitfalls

1. **Context expiry risk** — This project MUST survive session ends. Always verify code on disk after edits. The repo is the source of truth.
2. **TemplateResponse bug** — If upgrading FastAPI: use `templates.TemplateResponse(request, "index.html")` NOT the old dict-style. Also `templates.env.cache.clear()` if templates are stale.
3. **Port 3456 conflict** — If the server won't start, check for old uvicorn processes with `lsof -i :3456` or `ps aux | grep uvicorn`.
4. **Python cache** — After patching `.py` files, clear `__pycache__` with `find . -type d -name __pycache__ -exec rm -rf {} +` if changes don't seem to take effect.
5. **Static files** — `app.js` serves from `/static/app.js`. If the browser gets 404, check `main.py` has `app.mount("/static", ...)`.

---

## Next Session Priority Pick

When resuming, the user likely wants **ONE** of these:

1. **Finish the logo** — Get the glass effect exactly right (iOS candy / Aero).
2. **Rebuild project detail page** — Make clicking a project actually show files, agents, tasks.
3. **Implement comparison mode** — The side-by-side agent comparison feature.
4. **Clean up DB** — Remove old `__mkdir_test` rows if any remain, verify project paths match disk.

**Ask the user which to prioritize.** Don't just start coding — confirm the direction first.
