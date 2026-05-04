"""
Thumbtack v1.1 — Multi-Agent Orchestrator
File browser · Agent comparison · Task queue
"""
import os, asyncio, subprocess, sqlite3, json
from typing import Dict, Optional, List
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, path TEXT NOT NULL,
        description TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        agent_type TEXT NOT NULL DEFAULT 'custom',
        command TEXT,
        pid INTEGER, status TEXT DEFAULT 'idle',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS agent_output (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        output TEXT, is_stderr INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        task_text TEXT NOT NULL, status TEXT DEFAULT 'pending',
        agent_id INTEGER, result TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS github_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        username TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        default_branch TEXT NOT NULL DEFAULT 'main',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit(); conn.close()

# ── AgentProcess ────────────────────────────────────────────────────────
class AgentProcess:
    def __init__(self, aid: int, atype: str, proj_path: str, cmd: Optional[str]):
        self.aid = aid; self.atype = atype; self.path = proj_path; self.cmd = cmd
        self.proc: subprocess.Popen | None = None
        self._read_task: asyncio.Task | None = None
        self._clients: List[WebSocket] = []

    async def start(self):
        cmds = {
            "claude": (["claude","-p","--cwd",self.path] if os.path.exists("/usr/local/bin/claude") else ["python","-c","print('claude command placeholder: ',input())"]),
            "codex": ["codex"] if os.path.exists("/usr/local/bin/codex") else ["python","-c","print('codex placeholder:',input())"],
            "opencode": ["opencode"] if os.path.exists("/usr/local/bin/opencode") else ["python","-c","print('opencode placeholder:',input())"],
            "openclaw": ["openclaw"] if os.path.exists("/usr/local/bin/openclaw") else ["python","-c","print('openclaw placeholder:',input())"],
            "aider": ["aider","--no-auto-commits"] if os.path.exists("/usr/local/bin/aider") else ["python","-c","print('aider placeholder:',input())"],
            "custom": ([] if not self.cmd else self.cmd.split())
        }
        cmd = self.cmd.split() if self.cmd else cmds.get(self.atype, [])
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
                    if line: await self._broadcast(line.rstrip(), is_err)
                except: pass
            await asyncio.sleep(0.05)
        # flush remaining
        if self.proc:
            for pipe in [self.proc.stdout, self.proc.stderr]:
                try:
                    rem = pipe.read()
                    if rem:
                        for ln in rem.splitlines(): await self._broadcast(ln.rstrip(), pipe==self.proc.stderr)
                except: pass
        await self._broadcast("[Agent process ended]", False)

    async def _broadcast(self, line: str, is_err: bool):
        dead=[]
        for ws in list(self._clients):
            try: await ws.send_json({"stream":"stderr" if is_err else "stdout","data":line})
            except: dead.append(ws)
        for d in dead:
            if d in self._clients: self._clients.remove(d)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT INTO agent_output (agent_id,output,is_stderr) VALUES (?,?,?)",(self.aid,line,1 if is_err else 0))
        conn.commit(); conn.close()

    async def send(self, cmd: str):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(cmd+"\n"); self.proc.stdin.flush()
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
app = FastAPI(title="Thumbtack", version="1.1.0")
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
    cur.execute("SELECT output as line, is_stderr as stream, created_at FROM agent_output WHERE agent_id=? ORDER BY created_at DESC LIMIT ?",(aid,limit))
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

# ─── Task Queue ────────────────────────────────────────────────────────
@app.get("/api/projects/{pid}/tasks")
async def list_tasks(pid: int):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC", (pid,))
    rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

@app.post("/api/projects/{pid}/tasks")
async def add_task(pid: int, data: dict):
    text = data.get("task_text", "").strip()
    if not text: raise HTTPException(400, "task_text required")
    conn = _db(); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (project_id, task_text, status) VALUES (?,?,?)" ,(pid, text, "pending"))
    conn.commit(); tid = cur.lastrowid
    cur.execute("SELECT * FROM tasks WHERE id=?", (tid,)); row = dict(cur.fetchone())
    conn.close(); return row

@app.delete("/api/tasks/{tid}")
async def delete_task(tid: int):
    conn = _db(); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id=?", (tid,)); conn.commit(); conn.close()
    return {"status":"deleted"}

@app.post("/api/tasks/{tid}/run")
async def run_task(tid: int, agent_id: int = Query(...)):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id=?", (tid,)); task = cur.fetchone()
    if not task: conn.close(); raise HTTPException(404)
    # Get agent
    cur.execute("SELECT * FROM agents WHERE id=?", (agent_id,)); agent = cur.fetchone()
    if not agent: conn.close(); raise HTTPException(404, "Agent not found")
    conn.close()
    if task["status"] in ("running", "done"):
        raise HTTPException(400, f"Task already {task['status']}")
    # Forward to agent
    if agent_id in ACTIVE:
        await ACTIVE[agent_id].send(task["task_text"])
        conn = _db(); cur = conn.cursor()
        cur.execute("UPDATE tasks SET status=?, agent_id=? WHERE id=?", ("running", agent_id, tid))
        conn.commit(); conn.close()
        # mark done after a short delay (fire-and-forget)
        asyncio.create_task(_mark_task_done(tid, agent_id, "Dispatched"))
        return {"status":"running"}
    raise HTTPException(400, "Agent not active")

async def _mark_task_done(tid: int, aid: int, result: str):
    await asyncio.sleep(2)  # give time for output
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE tasks SET status=?, result=?, completed_at=CURRENT_TIMESTAMP WHERE id=?", ("done", result, tid))
    conn.commit(); conn.close()

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
    cur.execute("SELECT output as line, is_stderr FROM agent_output WHERE agent_id=? ORDER BY created_at DESC LIMIT 100", (aid,))
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
@app.get("/api/health")
async def health(): return {"status":"ok","agents":len(ACTIVE)}

# Catch-all SPA redirect
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_catchall(r: Request, path: str):
    return templates.TemplateResponse(r, "index.html")

# ─── Init ──────────────────────────────────────────────────────────────
init_db()
