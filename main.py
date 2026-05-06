"""
Thumbtack v1.1 — Multi-agent orchestration
File browser · Agent comparison · Task queue
"""
import os, asyncio, subprocess, sqlite3, json
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

# Load .env from the thumbtack directory
DOTENV_PATH = Path(__file__).resolve().parent / ".env"
if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)

TZ = ZoneInfo("Australia/Brisbane")
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from contextlib import asynccontextmanager
from database import init_db, add_agent_log, get_agent_logs, create_task as db_create_task, list_tasks as db_list_tasks, get_task as db_get_task, update_task_status, create_subtasks, get_subtasks, get_pending_tasks, get_queued_tasks, get_running_tasks, delete_task as db_delete_task, get_task_outputs

from worker_pool import get_pool, start_pool, stop_pool
from task_decomposer import decompose_task
import azure_client

# ── Paths ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "thumbtack.db")

# ── Pydantic models ─────────────────────────────────────────────────────
class _ProjectIn(BaseModel):
    name: str
    path: str
    description: Optional[str] = ""

class _AgentIn(BaseModel):
    project_id: int
    agent_type: str
    command: Optional[str] = None

class _CmdIn(BaseModel):
    command: str

# ── DB helper ───────────────────────────────────────────────────────────
def _db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── Orchestrator Heartbeat ────────────────────────────────────────────
HEARTBEAT_INTERVAL = 10   # 10 seconds — quick dispatch during dev
HEARTBEAT_TASK: asyncio.Task | None = None
HEARTBEAT_STARTED = False  # idempotency guard
ORCHESTRATOR_STATE = {
    "last_wake": None,
    "status": "idle",
    "active_tasks": 0,
    "total_ticks": 0,
}

async def _orchestrator_heartbeat():
    """Background loop: tick → pool.dispatch."""
    await start_pool()
    while True:
        ORCHESTRATOR_STATE["last_wake"] = datetime.now(TZ).isoformat()
        ORCHESTRATOR_STATE["total_ticks"] += 1

        try:
            pool = get_pool()
            await pool.tick()

            running = get_running_tasks()
            queued  = get_queued_tasks()
            running_count = len(running)
            queued_count  = len(queued)
            ORCHESTRATOR_STATE["active_tasks"] = running_count

            if running_count == 0 and queued_count == 0:
                ORCHESTRATOR_STATE["status"] = "idle"
            elif running_count > 0:
                ORCHESTRATOR_STATE["status"] = "running"
            else:
                ORCHESTRATOR_STATE["status"] = "scanning"

        except Exception as e:
            add_agent_log("AGENT_ERROR", f"Heartbeat tick failed: {e}")
            ORCHESTRATOR_STATE["status"] = "error"

        await asyncio.sleep(HEARTBEAT_INTERVAL)

# ── Agent Compatibility Shim ────────────────────────────────────────────
class AgentProcess:
    """Legacy free-running agent (spawn button). Wraps a subprocess directly."""
    def __init__(self, aid: int, atype: str, proj_path: str, cmd: Optional[str]):
        self.aid = aid; self.atype = atype; self.path = proj_path; self.cmd = cmd
        self.proc: subprocess.Popen | None = None
        self._read_task: asyncio.Task | None = None
        self._clients: List[WebSocket] = []

    async def start(self):
        cmds = {
            "claude":   (["/home/administrator/.local/bin/claude","-p","--cwd",self.path]
                         if os.path.isfile("/home/administrator/.local/bin/claude")
                         else ["python","-c","print('claude placeholder:',input())"]),
            "codex":    ["codex"] if os.path.isfile("/usr/local/bin/codex") else ["python","-c","print('codex placeholder:',input())"],
            "aider":    ["aider","--no-auto-commits"] if os.path.isfile("/usr/local/bin/aider") else ["python","-c","print('aider placeholder:',input())"],
            "custom":   ([] if not self.cmd else self.cmd.split())
        }
        cmd = self.cmd.split() if self.cmd else cmds.get(self.atype, ["python","-c","print('placeholder:',input())"])
        if not cmd: raise ValueError(f"No command for {self.atype}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, cwd=self.path, text=True, bufsize=1)
        self._read_task = asyncio.create_task(self._reader())

    async def _reader(self):
        loop = asyncio.get_event_loop()
        while self.proc and self.proc.poll() is None:
            for pipe, is_err in [(self.proc.stdout, False), (self.proc.stderr, True)]:
                try:
                    line = await loop.run_in_executor(None, pipe.readline)
                    if line: await self._broadcast(line.rstrip("\n"), is_err)
                except: pass
            await asyncio.sleep(0.05)
        # flush remaining
        if self.proc:
            for pipe, is_err in [(self.proc.stdout, False), (self.proc.stderr, True)]:
                try:
                    rem = pipe.read()
                    if rem:
                        for ln in rem.splitlines(): await self._broadcast(ln.rstrip("\n"), pipe==self.proc.stderr)
                except: pass
        await self._broadcast("[Agent process ended]", False)

    async def _broadcast(self, line: str, is_err: bool):
        dead=[]
        stream = "stderr" if is_err else "stdout"
        for ws in list(self._clients):
            try: await ws.send_json({"stream":stream,"data":line})
            except: dead.append(ws)
        for d in dead:
            if d in self._clients: self._clients.remove(d)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT INTO agent_output (agent_id,output,is_stderr) VALUES (?,?,?)",
                  (self.aid, line, 1 if is_err else 0))
        conn.commit(); conn.close()

    async def send(self, cmd: str):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(cmd+"\\n"); self.proc.stdin.flush()
            await self._broadcast(">>> "+cmd, False)

    async def stop(self):
        if self.proc:
            self.proc.terminate()
            try: self.proc.wait(timeout=3)
            except: self.proc.kill()
        if self._read_task:
            self._read_task.cancel()
            try: await self._read_task
            except asyncio.CancelledError: pass
        for ws in self._clients:
            try: await ws.close()
            except: pass
        self._clients.clear()

    def register_client(self, ws: WebSocket): self._clients.append(ws)
    def unregister_client(self, ws: WebSocket):
        if ws in self._clients: self._clients.remove(ws)

ACTIVE: Dict[int, AgentProcess] = {}

# ── FastAPI ─────────────────────────────────────────────────────────────
def _is_fresh_restart():
    """True if a SYSTEM/RESTART log exists within the last 60 seconds."""
    conn = _db()
    rows = conn.execute(
        "SELECT level, timestamp FROM agent_log WHERE level IN ('SYSTEM','RESTART') ORDER BY id DESC LIMIT 1"
    ).fetchall()
    conn.close()
    if not rows:
        return False
    ts_str = rows[0]["timestamp"]
    try:
        ts = datetime.fromisoformat(ts_str)
        # DB timestamps may be naive; attach Brisbane tz if needed
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ)
        now = datetime.now(TZ)
        return (now - ts).total_seconds() < 60
    except Exception:
        return False

def _reconcile_running_agents():
    """Mark agents whose PID no longer exists as failed, and cascade to tasks."""
    import os
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT id, pid FROM agents WHERE status='running' AND pid IS NOT NULL")
    dead = []
    for row in cur.fetchall():
        try:
            os.kill(row["pid"], 0)
        except (ProcessLookupError, OSError):
            dead.append(row["id"])
    if dead:
        placeholders = ",".join("?" * len(dead))
        cur.execute(f"UPDATE agents SET status='failed' WHERE id IN ({placeholders})", dead)
        cur.execute(
            f"UPDATE tasks SET status='failed', result='Agent process no longer running' "
            f"WHERE status='running' AND assigned_agent_id IN ({placeholders})", dead
        )
        conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global HEARTBEAT_TASK, HEARTBEAT_STARTED
    init_db()
    _reconcile_running_agents()
    is_restart = _is_fresh_restart()
    event_type = "RESTART" if is_restart else "SYSTEM"
    msg = (
        "ThumbTack orchestrator restarted after crash. Heartbeat armed."
        if is_restart else
        "ThumbTack orchestrator started. Heartbeat armed."
    )
    add_agent_log(event_type, msg)
    if not HEARTBEAT_STARTED:
        HEARTBEAT_STARTED = True
        HEARTBEAT_TASK = asyncio.create_task(_orchestrator_heartbeat())
    yield
    if HEARTBEAT_TASK and not HEARTBEAT_TASK.done():
        HEARTBEAT_TASK.cancel()
        try:
            await HEARTBEAT_TASK
        except asyncio.CancelledError:
            pass
    add_agent_log("SYSTEM", "ThumbTack orchestrator shutting down.")

app = FastAPI(title="Thumbtack", version="1.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR,"static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR,"templates"))

# ── Pages ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(r: Request): return templates.TemplateResponse(r, "index.html")

# ── Presets ───────────────────────────────────────────────────────────
PRESETS = {
    "claude": [{"label":"Analyze", "command":"/analyze this codebase"},
               {"label":"Fix", "command":"/fix the most critical issue"},
               {"label":"Test", "command":"/test all files"},
               {"label":"Commit", "command":"/commit"}],
    "codex": [{"label":"Review", "command":"Review this code"},
              {"label":"Refactor", "command":"Refactor for readability"},
              {"label":"Docs", "command":"Add docstrings"},
              {"label":"Type", "command":"Add type hints"}],
    "aider": [{"label":"Add", "command":"Add a new feature"},
              {"label":"Fix bug", "command":"Fix the main bug"},
              {"label":"Lint", "command":"Run linter and fix"}],
    "default": [{"label":"Hello", "command":"hello"}]
}

# ── Projects ────────────────────────────────────────────────────────────
@app.get("/api/projects")
async def list_projects():
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    # count agents
    for r in rows:
        cur.execute("SELECT COUNT(*) FROM agents WHERE project_id=?", (r["id"],))
        r["agent_count"] = cur.fetchone()[0]
    conn.close(); return rows

@app.post("/api/projects")
async def create_project(data: _ProjectIn):
    raw = data.path.strip()
    if raw.startswith('~') or raw.startswith('/'):
        resolved = os.path.expanduser(raw)
    else:
        resolved = os.path.join(os.path.expanduser('~'), 'thumbtack_projects', raw)
    resolved = os.path.abspath(resolved)
    if not os.path.exists(resolved):
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"Cannot create project path '{resolved}': {e}")

    conn = _db(); cur = conn.cursor()
    cur.execute("INSERT INTO projects (name,path,description) VALUES (?,?,?)",(data.name,resolved,data.description or ""))
    conn.commit(); pid = cur.lastrowid
    cur.execute("SELECT * FROM projects WHERE id=?",(pid,)); row = dict(cur.fetchone())
    conn.close(); return row

@app.get("/api/projects/{pid}")
async def get_project(pid: int):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id=?",(pid,)); row = cur.fetchone()
    if not row: conn.close(); raise HTTPException(404)
    proj = dict(row)
    cur.execute("SELECT * FROM agents WHERE project_id=? ORDER BY created_at DESC",(pid,))
    proj["agents"] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC",(pid,))
    proj["tasks"] = [dict(r) for r in cur.fetchall()]
    # file listing
    if os.path.isdir(proj["path"]):
        try:
            proj["files"] = sorted([{"name":e.name,"is_dir":e.is_dir(),"path":os.path.relpath(e.path,proj["path"])} for e in os.scandir(proj["path"])], key=lambda x:(not x["is_dir"],x["name"].lower()))
        except: proj["files"] = []
    else: proj["files"] = []
    conn.close(); return proj

@app.delete("/api/projects/{pid}")
async def delete_project(pid: int):
    conn = _db(); cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id=?",(pid,)); conn.commit(); conn.close()
    return {"status":"deleted"}

# ─── Agents ──────────────────────────────────────────────────────────────
@app.post("/api/agents")
async def spawn_agent(data: _AgentIn):
    print(f"[Thumbtack] Starting agent: {data.agent_type} in project {data.project_id}")
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT path FROM projects WHERE id=?", (data.project_id,))
    row = cur.fetchone()
    if not row: conn.close(); raise HTTPException(404, "Project not found")
    proj_path = row[0]

    # default command if empty
    cmd = data.command or None

    cur.execute("INSERT INTO agents (project_id,agent_type,command,status) VALUES (?,?,?,?)",
                (data.project_id, data.agent_type, cmd, "running"))
    conn.commit(); aid = cur.lastrowid; conn.close()

    ap = AgentProcess(aid, data.agent_type, proj_path, cmd)
    try:
        await ap.start()
        ACTIVE[aid] = ap
        # update pid
        conn = _db(); cur = conn.cursor()
        cur.execute("UPDATE agents SET pid=? WHERE id=?", (ap.proc.pid if ap.proc else None, aid))
        conn.commit(); conn.close()
    except Exception as e:
        conn = _db(); cur = conn.cursor()
        cur.execute("UPDATE agents SET status=? WHERE id=?", ("error", aid))
        conn.commit(); conn.close()
        raise HTTPException(500, str(e))

    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM agents WHERE id=?", (aid,)); result = dict(cur.fetchone())
    conn.close(); return result

@app.get("/api/agents/{aid}")
async def get_agent(aid: int):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM agents WHERE id=?",(aid,)); row = cur.fetchone()
    conn.close()
    if not row: raise HTTPException(404)
    return dict(row)

@app.post("/api/agents/{aid}/command")
async def send_cmd(aid: int, data: _CmdIn):
    if aid not in ACTIVE: raise HTTPException(404, "Agent not running")
    await ACTIVE[aid].send(data.command); return {"status":"sent"}

@app.post("/api/agents/{aid}/stop")
async def stop_agent(aid: int):
    if aid in ACTIVE:
        await ACTIVE[aid].stop(); del ACTIVE[aid]
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE agents SET status=? WHERE id=?",("stopped",aid)); conn.commit(); conn.close()
    return {"status":"stopped"}

@app.delete("/api/agents/{aid}")
async def kill_agent(aid: int):
    if aid in ACTIVE:
        await ACTIVE[aid].stop(); del ACTIVE[aid]
    conn = _db(); cur = conn.cursor()
    cur.execute("DELETE FROM agents WHERE id=?",(aid,)); conn.commit(); conn.close()
    return {"status":"killed"}

# ─── Agent output ────────────────────────────────────────────────────────
@app.get("/api/agents/{aid}/output")
async def get_output(aid: int, limit: int=200):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT output as line, is_stderr as stream, created_at FROM agent_output WHERE agent_id=? ORDER BY id DESC LIMIT ?",(aid,limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        if isinstance(r.get("stream"), int):
            r["stream"] = "stderr" if r["stream"] else "stdout"
    return rows[::-1]

@app.get("/api/presets/{agent_type}")
async def get_presets(agent_type: str):
    return PRESETS.get(agent_type, PRESETS["default"])

# ─── File Browser ───────────────────────────────────────────────────────
@app.get("/api/projects/{pid}/files")
async def list_files(pid: int, path: str=Query("")):
    proj = await get_project(pid)
    base = os.path.abspath(proj["path"])
    target = os.path.abspath(os.path.join(base, path))
    if not target.startswith(base): raise HTTPException(400, "path traversal")
    items = []
    try:
        for entry in os.scandir(target):
            items.append({
                "name": entry.name,
                "path": os.path.relpath(entry.path, base),
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
                "ext": os.path.splitext(entry.name)[1].lower() if entry.is_file() else ""
            })
    except: raise HTTPException(403)
    items.sort(key=lambda x:(not x["is_dir"], x["name"].lower()))
    return {"base": base, "rel": os.path.relpath(target, base), "items": items}

@app.get("/api/projects/{pid}/files/read")
async def read_file(pid: int, filepath: str=Query(...)):
    proj = await get_project(pid)
    base = os.path.abspath(proj["path"])
    target = os.path.abspath(os.path.join(base, filepath))
    if not target.startswith(base) or not os.path.isfile(target): raise HTTPException(400, "Invalid file path")
    if os.path.getsize(target) > 2*1024*1024: raise HTTPException(413, "File too large")
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": filepath, "content": content}
    except Exception as e: raise HTTPException(500, str(e))

# ─── Comparison ──────────────────────────────────────────────────────────
@app.post("/api/comparison")
async def spawn_comparison(data: dict):
    pid = data.get("project_id"); left_type = data.get("left_type","claude"); right_type = data.get("right_type","codex")
    command = data.get("command","")
    proj = await get_project(pid)
    left = await spawn_agent(_AgentIn(project_id=pid, agent_type=left_type, command=command))
    right = await spawn_agent(_AgentIn(project_id=pid, agent_type=right_type, command=command))
    return {"comparison_id": f"{left['id']}-{right['id']}", "left_agent_id":left["id"], "right_agent_id":right["id"],
            "left_type":left_type, "right_type":right_type, "command":command}

# ─── Task Queue (Phase 2) ────────────────────────────────────────────────────────
@app.get("/api/projects/{pid}/tasks")
async def list_tasks(pid: int):
    rows = db_list_tasks(pid)
    return rows

@app.get("/api/tasks/{tid}")
async def get_task(tid: int):
    row = db_get_task(tid)
    if not row: raise HTTPException(404, "Task not found")
    row["subtasks"] = get_subtasks(tid)
    return row

@app.post("/api/projects/{pid}/tasks")
async def create_task(pid: int, data: dict):
    title = data.get("title", "").strip()
    if not title: raise HTTPException(400, "title required")
    description = data.get("description", "").strip()
    priority = data.get("priority", 3)
    try:
        priority = int(priority)
        if priority < 1 or priority > 5: priority = 3
    except: priority = 3
    tid = db_create_task(pid, title, description, priority)
    row = db_get_task(tid)
    add_agent_log("TASK_CREATED", f"Task #{tid} created: {title}", task_id=tid, project_id=pid)
    return row

@app.patch("/api/tasks/{tid}")
async def update_task(tid: int, data: dict):
    """Generic update: status, title, description, priority."""
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    conn = _db(); cur = conn.cursor()
    fields = []
    vals = []
    if "status" in data: fields.append("status=?"); vals.append(data["status"])
    if "title" in data: fields.append("title=?"); vals.append(data["title"])
    if "description" in data: fields.append("description=?"); vals.append(data["description"])
    if "priority" in data: fields.append("priority=?"); vals.append(data["priority"])
    if "result" in data: fields.append("result=?"); vals.append(data["result"])
    if not fields: conn.close(); raise HTTPException(400, "No fields to update")
    vals.append(tid)
    cur.execute(f"UPDATE tasks SET {','.join(fields)} WHERE id=?", vals)
    conn.commit()
    cur.execute("SELECT * FROM tasks WHERE id=?", (tid,)); row = dict(cur.fetchone())
    conn.close()
    add_agent_log("TASK_UPDATED", f"Task #{tid} updated: {','.join(fields)}", task_id=tid)
    return row

@app.post("/api/tasks/{tid}/plan")
async def auto_plan_task(tid: int, data: dict = None):
    """Auto-decompose a task using the LLM planner.
    Body (optional): {"custom_prompt": "...extra context..."}
    """
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    if task["status"] not in ("pending", "planning"):
        raise HTTPException(400, f"Cannot plan task with status '{task['status']}'")

    # Prevent duplicate subtasks if task was already planned
    existing_subtasks = get_subtasks(tid)
    if existing_subtasks:
        raise HTTPException(400, f"Task #{tid} already has {len(existing_subtasks)} subtasks. Reject or delete them before re-planning.")

    custom_prompt = (data or {}).get("custom_prompt")
    result = await decompose_task(tid, custom_prompt=custom_prompt)

    if not result["ok"]:
        raise HTTPException(500, result["error"])

    # Convert validated subtasks → DB rows
    subtask_specs = result["subtasks"]
    if not subtask_specs:
        raise HTTPException(500, "Planner returned no subtasks")

    update_task_status(tid, "planning")
    ids = create_subtasks(tid, task["project_id"], subtask_specs)

    # Update subtask metadata (agent_type, estimated_minutes) — DB schema may need extension
    conn = _db(); cur = conn.cursor()
    for idx, sid in enumerate(ids):
        spec = subtask_specs[idx]
        cur.execute(
            "UPDATE tasks SET assigned_agent_type=?, command=? WHERE id=?",
            (spec["agent_type"], f"# Estimated: {spec['estimated_minutes']}min\n{spec['description']}", sid)
        )
    conn.commit(); conn.close()

    row = db_get_task(tid)
    row["subtasks"] = get_subtasks(tid)
    row["new_subtask_ids"] = ids
    add_agent_log("TASK_PLANNED", f"Task #{tid} auto-decomposed into {len(ids)} subtasks", task_id=tid)
    return row

@app.post("/api/tasks/{tid}/decompose")
async def decompose_task_manual(tid: int, data: dict):
    """Human or orchestrator proposes subtasks. Task goes pending→planning.
    Body: {"subtasks": [{"title": "...", "description": "...", "priority": 3}, ...]}
    """
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    existing_subtasks = get_subtasks(tid)
    if existing_subtasks:
        raise HTTPException(400, f"Task #{tid} already has {len(existing_subtasks)} subtasks.")
    subtasks = data.get("subtasks", [])
    if not isinstance(subtasks, list) or not subtasks:
        raise HTTPException(400, "subtasks array required")
    # Update parent to planning
    update_task_status(tid, "planning")
    # Create subtasks (status=planning_subtask — they won't run until parent is approved)
    ids = create_subtasks(tid, task["project_id"], subtasks)
    row = db_get_task(tid)
    row["subtasks"] = get_subtasks(tid)
    row["new_subtask_ids"] = ids
    add_agent_log("TASK_DECOMPOSED", f"Task #{tid} decomposed into {len(ids)} subtasks", task_id=tid)
    return row

@app.post("/api/tasks/{tid}/approve")
async def approve_task(tid: int):
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    if task["status"] not in ("pending", "planning"):
        raise HTTPException(400, f"Cannot approve task with status '{task['status']}'")
    # Mark parent approved
    update_task_status(tid, "approved")
    # Change subtasks from 'queued' to 'queued' — they stay queued for the heartbeat to pick up
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE tasks SET status='queued' WHERE parent_task_id=? AND status='planning_subtask'", (tid,))
    # Actually subtasks already have status='queued', but we can leave them
    conn.commit(); conn.close()
    add_agent_log("TASK_APPROVED", f"Task #{tid} approved. Subtasks queued for execution.", task_id=tid)
    return db_get_task(tid)

@app.post("/api/tasks/{tid}/reject")
async def reject_task(tid: int):
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    update_task_status(tid, "rejected")
    conn = _db(); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE parent_task_id=?", (tid,))
    conn.commit(); conn.close()
    add_agent_log("TASK_REJECTED", f"Task #{tid} rejected. Subtasks removed.", task_id=tid)
    return {"status": "rejected", "task_id": tid}

@app.delete("/api/tasks/{tid}")
async def delete_task(tid: int):
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    # Delete subtasks first
    conn = _db(); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE parent_task_id=?", (tid,))
    conn.commit(); conn.close()
    db_delete_task(tid)
    add_agent_log("TASK_DELETED", f"Task #{tid} deleted", task_id=tid)
    return {"status": "deleted", "task_id": tid}

# Legacy task_text endpoint (redirects to new create)
@app.post("/api/projects/{pid}/tasks/legacy")
async def add_task_legacy(pid: int, data: dict):
    text = data.get("task_text", "").strip()
    if not text: raise HTTPException(400, "task_text required")
    tid = db_create_task(pid, text, "", 3)
    row = db_get_task(tid)
    add_agent_log("TASK_CREATED", f"Legacy task #{tid} created", task_id=tid, project_id=pid)
    return row

# ─── WebSocket ──────────────────────────────────────────────────────────
@app.websocket("/ws/agents/{aid}")
async def ws_agent(websocket: WebSocket, aid: int):
    await websocket.accept()
    if aid not in ACTIVE:
        await websocket.send_json({"type":"error","message":"Agent not running"})
        await websocket.close(); return
    ACTIVE[aid].register_client(websocket)
    # send history
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT output as line, is_stderr FROM agent_output WHERE agent_id=? ORDER BY id DESC LIMIT 100", (aid,))
    for row in cur.fetchall()[::-1]:
        await websocket.send_json({"stream":"stderr" if row["is_stderr"] else "stdout","data":row["output"]})
    conn.close()
    try:
        while True:
            data = await websocket.receive_text()
            try: payload = json.loads(data)
            except: continue
            if payload.get("type") == "command" and aid in ACTIVE:
                await ACTIVE[aid].send(payload.get("command",""))
    except WebSocketDisconnect: pass
    finally:
        if aid in ACTIVE: ACTIVE[aid].unregister_client(websocket)

# ─── Task WebSocket (Phase 3) ────────────────────────────────────────────
@app.websocket("/ws/tasks/{tid}")
async def ws_task(websocket: WebSocket, tid: int):
    """Stream output from a task-bound agent (Phase 3 WorkerPool)."""
    await websocket.accept()
    pool = get_pool()
    task_agent = pool.get_agent(tid)
    if not task_agent:
        await websocket.send_json({"type":"error","message":"Task not running"})
        await websocket.close(); return
    task_agent.register_ws(websocket)
    # send recent history from DB (via the agent_id)
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT output, is_stderr FROM agent_output WHERE agent_id=? ORDER BY id DESC LIMIT 200",
                (task_agent.agent_id,))
    for row in cur.fetchall()[::-1]:
        await websocket.send_json({"stream":"stderr" if row[1] else "stdout","data":row[0]})
    conn.close()
    try:
        while True:
            data = await websocket.receive_text()
            try: payload = json.loads(data)
            except: continue
            if payload.get("type") == "command":
                ta = pool.get_agent(tid)
                if ta:
                    await ta.send_cmd(payload.get("command",""))
    except WebSocketDisconnect: pass
    finally:
        ta = pool.get_agent(tid)
        if ta:
            ta.unregister_ws(websocket)

@app.post("/api/tasks/{tid}/dispatch")
async def dispatch_task(tid: int, data: dict = None):
    """Manual dispatch a queued task to the worker pool."""
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    if task["status"] != "queued":
        raise HTTPException(400, f"Task must be 'queued', is '{task['status']}'")
    pool = get_pool()
    await pool.tick()   # triggers immediate dispatch attempt
    return {"status": "dispatched", "task_id": tid}

@app.post("/api/tasks/{tid}/stop")
async def stop_task(tid: int):
    """Force-stop a running task."""
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    pool = get_pool()
    await pool.stop_task(tid)
    add_agent_log("TASK_STOPPED", f"Task #{tid} stopped by user", task_id=tid)
    return {"status": "stopped", "task_id": tid}

@app.get("/api/tasks/{tid}/output")
async def task_output(tid: int, limit: int = 200):
    task = db_get_task(tid)
    if not task: raise HTTPException(404, "Task not found")
    rows = get_task_outputs(tid, limit=limit)
    for r in rows:
        r["is_stderr"] = bool(r.get("is_stderr"))
    return {"task_id": tid, "outputs": rows}


# ─── Git ──────────────────────────────────────────────────────────
@app.get("/api/projects/{pid}/git/status")
async def git_status(pid: int):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        return {"repo_exists": False}
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-b"],
        cwd=path, capture_output=True, text=True
    )
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    branch = ""
    is_dirty = False
    modified, untracked, staged = [], [], []
    for ln in lines:
        if ln.startswith("## "):
            info = ln[3:]
            if "..." in info:
                branch = info.split("...")[0]
            else:
                branch = info.split(" ")[0]
        elif len(ln) >= 3:
            x, y, name = ln[0], ln[1], ln[3:]
            if x != "." or y != ".": is_dirty = True
            if x in "MADRC": staged.append(name)
            if y in "MD": modified.append(name)
            if x == "?" and y == "?": untracked.append(name)
    return {
        "repo_exists": True,
        "branch": branch,
        "is_dirty": is_dirty,
        "modified": modified,
        "untracked": untracked,
        "staged": staged,
        "ahead": branch.count("ahead") if branch else 0,
        "behind": branch.count("behind") if branch else 0,
    }

@app.get("/api/projects/{pid}/git/diff")
async def git_diff(pid: int, filepath: str = Query("")):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    cmd = ["git", "diff", "--no-color"]
    if filepath: cmd.append(filepath)
    result = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
    return {"diff": result.stdout or "", "file": filepath or "(all files)", "empty": not result.stdout.strip()}

@app.post("/api/projects/{pid}/git/init")
async def git_init(pid: int):
    proj = await get_project(pid)
    path = proj["path"]
    if os.path.isdir(os.path.join(path, ".git")):
        return {"status": "already_initialized"}
    subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "ThumbTack"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "thumbtack@local"], cwd=path, capture_output=True)
    return {"status": "initialized"}

@app.post("/api/projects/{pid}/git/commit")
async def git_commit(pid: int, data: dict):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    msg = data.get("message", "WIP commit").strip()
    if not msg: raise HTTPException(400, "Commit message required")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    result = subprocess.run(["git", "commit", "-m", msg], cwd=path, capture_output=True, text=True)
    if result.returncode == 0:
        return {"status": "committed", "message": msg}
    err = result.stderr.lower()
    if "nothing to commit" in err or result.stdout.lower().count("nothing"):
        return {"status": "nothing_to_commit", "message": "Nothing to commit, working tree clean"}
    raise HTTPException(500, result.stderr.strip() or "Commit failed")

# ─── GitHub Remote & Settings ──────────────────────────────────────────
from database import get_github_settings, save_github_settings, delete_github_settings

@app.get("/api/github/config")
async def get_github_config():
    cfg = get_github_settings()
    if not cfg:
        return {"configured": False, "username": "", "email": "", "default_branch": "main"}
    return {
        "configured": True,
        "username": cfg.get("username", ""),
        "email": cfg.get("email", ""),
        "token_present": bool(cfg.get("token", "")),
        "default_branch": cfg.get("default_branch", "main"),
    }

@app.post("/api/github/config")
async def post_github_config(data: dict):
    username = data.get("username","").strip()
    email    = data.get("email","").strip()
    token    = data.get("token")   # None if omitted — preserve existing
    branch   = data.get("default_branch","main").strip()
    if not username: raise HTTPException(400,"GitHub username required")
    save_github_settings(username, email, token, branch)
    return {"status":"saved"}

@app.delete("/api/github/config")
async def clear_github_config():
    delete_github_settings()
    return {"status": "cleared"}

@app.post("/api/projects/{pid}/git/remote")
async def add_git_remote(pid: int, data: dict):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    url = data.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Remote URL required")
    cfg = get_github_settings()
    # If HTTPS repo URL and we have token, use it for auth in remote
    if "github.com" in url and cfg.get("token"):
        # Convert https://github.com/user/repo.git to https://token@github.com/user/repo.git
        if url.startswith("https://") and "@" not in url.replace("://", ""):
            url = url.replace("https://", f"https://{cfg['token']}@")
    subprocess.run(["git", "remote", "remove", "origin"], cwd=path, capture_output=True)
    result = subprocess.run(["git", "remote", "add", "origin", url], cwd=path, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(400, result.stderr.strip() or "Failed to add remote")
    # Set user config for this repo
    if cfg.get("username"):
        subprocess.run(["git", "config", "user.name", cfg["username"]], cwd=path, capture_output=True)
    if cfg.get("email"):
        subprocess.run(["git", "config", "user.email", cfg["email"]], cwd=path, capture_output=True)
    return {"status": "remote_added", "url": url.split("@")[-1] if "@" in url else url}

@app.get("/api/projects/{pid}/git/remote")
async def get_git_remote_status(pid: int):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        return {"has_remote": False}
    result = subprocess.run(["git", "remote", "-v"], cwd=path, capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")
    remotes = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            remotes[parts[0]] = parts[1]
    fetch_url = remotes.get("origin", "")
    # Mask any token in the URL for display
    display_url = fetch_url
    if "@" in display_url and display_url.startswith("https://"):
        display_url = "https://" + display_url.split("@", 1)[1]
    return {"has_remote": bool(fetch_url), "url": display_url, "raw_url": fetch_url}

@app.post("/api/projects/{pid}/git/push")
async def git_push(pid: int, data: dict = None):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    branch = (data.get("branch", "main") if data else "main").strip()
    cfg = get_github_settings()
    # Ensure remote uses token if available
    rem_result = subprocess.run(["git", "remote", "-v"], cwd=path, capture_output=True, text=True)
    rem_lines = rem_result.stdout.strip().split("\n")
    has_origin = any("origin" in line for line in rem_lines)
    if not has_origin:
        raise HTTPException(400, "No remote origin configured")
    # Re-config remote with token if needed
    for line in rem_lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "origin":
            raw_url = parts[1]
            if "github.com" in raw_url and cfg.get("token") and "@" not in raw_url.replace("://", ""):
                new_url = raw_url.replace("https://", f"https://{cfg['token']}@")
                subprocess.run(["git", "remote", "set-url", "origin", new_url], cwd=path, capture_output=True)
            break
    result = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=path, capture_output=True, text=True
    )
    if result.returncode == 0:
        return {"status": "pushed", "branch": branch, "output": result.stdout.strip()}
    err = result.stderr.strip() or result.stdout.strip()
    raise HTTPException(400, err or "Push failed")

@app.post("/api/projects/{pid}/git/pull")
async def git_pull(pid: int, data: dict = None):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    branch = (data.get("branch", "main") if data else "main").strip()
    cfg = get_github_settings()
    # Ensure remote uses token if available
    rem_result = subprocess.run(["git", "remote", "-v"], cwd=path, capture_output=True, text=True)
    rem_lines = rem_result.stdout.strip().split("\n")
    for line in rem_lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "origin":
            raw_url = parts[1]
            if "github.com" in raw_url and cfg.get("token") and "@" not in raw_url.replace("://", ""):
                new_url = raw_url.replace("https://", f"https://{cfg['token']}@")
                subprocess.run(["git", "remote", "set-url", "origin", new_url], cwd=path, capture_output=True)
            break
    result = subprocess.run(
        ["git", "pull", "origin", branch],
        cwd=path, capture_output=True, text=True
    )
    if result.returncode == 0:
        return {"status": "pulled", "branch": branch, "output": result.stdout.strip()}
    err = result.stderr.strip() or result.stdout.strip()
    raise HTTPException(400, err or "Pull failed")

@app.get("/api/projects/{pid}/git/log")
async def git_log(pid: int, limit: int = Query(50)):
    proj = await get_project(pid)
    path = proj["path"]
    if not os.path.isdir(os.path.join(path, ".git")):
        raise HTTPException(400, "Not a git repository")
    result = subprocess.run(
        ["git", "log", f"--max-count={limit}", "--date=iso", "--pretty=format:%H|%h|%an|%ae|%ad|%s"],
        cwd=path, capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"commits": []}
    commits = []
    if result.stdout.strip():
        for ln in result.stdout.strip().split("\n"):
            parts = ln.split("|", 5)
            if len(parts) == 6:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "email": parts[3],
                    "date": parts[4],
                    "message": parts[5]
                })
    return {"commits": commits}

# ─── Health ────────────────────────────────────────────────────────────
# ─── Orchestrator Status ─────────────────────────────────────────────
@app.get("/api/orchestrator/status")
async def orchestrator_status():
    return {
        "status": ORCHESTRATOR_STATE["status"],
        "last_wake": ORCHESTRATOR_STATE["last_wake"],
        "total_ticks": ORCHESTRATOR_STATE["total_ticks"],
        "active_tasks": ORCHESTRATOR_STATE["active_tasks"],
        "heartbeat_interval": HEARTBEAT_INTERVAL,
    }

@app.get("/api/agent-log")
async def agent_log(limit: int = 50, level: str = None, project_id: int = None):
    logs = get_agent_logs(limit=limit, project_id=project_id, level=level)
    return {"logs": logs}

@app.get("/api/health")
async def health(): return {"status":"ok","agents":len(ACTIVE)}

# Catch-all SPA redirect
# ─── Placeholder Pages ───

@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Task management dashboard (placeholder)."""
    return templates.TemplateResponse(request, "tasks.html")

@app.get("/terminals", response_class=HTMLResponse)
async def terminals_page(request: Request):
    """Terminal management dashboard (placeholder)."""
    return templates.TemplateResponse(request, "terminals.html")


# ─── Top Spenders ────────────────────────────────────────────────────────
@app.get("/top-spenders", response_class=HTMLResponse)
async def top_spenders_page(request: Request):
    """Azure cost breakdown by resource group and service."""
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    lookback_days = int(os.getenv("AZURE_LOOKBACK_DAYS", "30").strip() or "30")
    top_n = int(os.getenv("AZURE_TOP_N", "50").strip() or "50")

    by_resource_group = []
    by_service = []
    overall_total_rg = "$0.00"
    overall_total_service = "$0.00"
    error = None

    if subscription_id:
        result = await azure_client.get_top_spenders(
            subscription_id, lookback_days=lookback_days, top_n=top_n
        )
        if isinstance(result, dict) and "error" in result:
            error = result["error"]
        else:
            by_resource_group = result.get("by_resource_group", [])
            by_service = result.get("by_service", [])
            if by_resource_group:
                overall_total_rg = f"${by_resource_group[0]['cost']:.2f}"
            if by_service:
                overall_total_service = f"${by_service[0]['cost']:.2f}"

    return templates.TemplateResponse(
        request,
        "top_spenders.html",
        {
            "request": request,
            "subscription_id": subscription_id,
            "lookback_days": lookback_days,
            "by_resource_group": by_resource_group,
            "by_service": by_service,
            "overall_total_rg": overall_total_rg,
            "overall_total_service": overall_total_service,
            "error": error,
        },
    )


# ─── RI Coverage ─────────────────────────────────────────────────────────
@app.get("/ri-coverage", response_class=HTMLResponse)
async def ri_coverage_page(request: Request):
    """Azure Reserved Instance ↔ Virtual Machine coverage report."""
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    matches = []
    stats = {"total": 0, "utilized": 0, "mismatched": 0, "unused": 0}
    error = None

    if subscription_id:
        ri_result = await azure_client.get_reserved_instances(subscription_id)
        if isinstance(ri_result, dict) and "error" in ri_result:
            error = ri_result["error"]
        else:
            ris = ri_result or []
            vm_result = await azure_client.get_virtual_machines(subscription_id)
            vms = vm_result or [] if not (isinstance(vm_result, dict) and "error" in vm_result) else []
            if isinstance(vm_result, dict) and "error" in vm_result:
                error = vm_result["error"]

            # Build lookup: (region, size) -> list of VMs
            vm_by_region_size: dict[tuple[str, str], List[dict]] = {}
            for vm in vms:
                key = (vm.get("region", "").lower(), vm.get("size", "").lower())
                vm_by_region_size.setdefault(key, []).append(vm)

            # Build VM names by region only for mismatch detection
            vms_by_region_only: dict[str, List[dict]] = {}
            for vm in vms:
                region = vm.get("region", "").lower()
                vms_by_region_only.setdefault(region, []).append(vm)

            for ri in ris:
                region = (ri.get("region") or "").lower()
                sku = (ri.get("sku") or "").lower()
                qty = ri.get("quantity", 1)

                direct_key = (region, sku)
                matched_vms = []
                if direct_key in vm_by_region_size:
                    matched_vms = vm_by_region_size[direct_key][:qty]

                if matched_vms and len(matched_vms) >= qty:
                    status = "utilized"
                elif matched_vms:
                    status = "mismatched"
                else:
                    # Check if any VM shares region or SKU (partial mismatch)
                    same_region = vms_by_region_only.get(region, [])
                    status = "mismatched" if (same_region or any(vm.get("size", "").lower() == sku for vm in vms)) else "unused"

                stats["total"] += 1
                stats[status] += 1

                matches.append({
                    "name": ri.get("name", "Unnamed"),
                    "sku": ri.get("sku", "—"),
                    "region": ri.get("region", "—"),
                    "quantity": qty,
                    "matched_vms": matched_vms,
                    "status": status,
                    "expiry_date": ri.get("expiry_date", "—"),
                    "reservation_id": ri.get("reservation_id", "—"),
                })

    return templates.TemplateResponse(
        request,
        "ri_coverage.html",
        {
            "request": request,
            "subscription_id": subscription_id,
            "matches": matches,
            "stats": stats,
            "error": error,
        },
    )


@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_catchall(r: Request, path: str):
    return templates.TemplateResponse(r, "index.html")

# ─── Init ──────────────────────────────────────────────────────────────
