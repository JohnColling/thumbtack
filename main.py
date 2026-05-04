"""
Thumbtack — Multi-Agent Orchestrator Dashboard
Self-contained, no external modules needed.
"""
import os, asyncio, subprocess, sqlite3
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DB = os.path.join(os.path.dirname(__file__), "thumbtack.db")

# ═══════════════════════════════════ DB ════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, path TEXT NOT NULL,
        description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        agent_type TEXT NOT NULL, command TEXT, status TEXT DEFAULT 'idle',
        pid INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS agent_output (
        id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
        output TEXT, is_stderr INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        command TEXT NOT NULL, status TEXT DEFAULT 'pending',
        assigned_agent_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

# ═════════════════════════════ Agent Runner ═══════════════════════════
class AgentProcess:
    def __init__(self, aid: int, atype: str, path: str, cmd: Optional[str]):
        self.aid = aid; self.atype = atype; self.path = path; self.cmd = cmd
        self.proc: subprocess.Popen | None = None
        self.task: asyncio.Task | None = None
        self.clients: List[WebSocket] = []
        self.lock = asyncio.Lock()

    async def start(self):
        cmds = {"claude": ["claude","-p"], "codex": ["codex"], "opencode": ["opencode"],
                "openclaw": ["openclaw"], "aider": ["aider","--no-git"], "custom": []}
        cmd = self.cmd or cmds.get(self.atype, [])
        if not cmd: raise ValueError(f"No command for {self.atype}")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=self.path, text=True, bufsize=1)
        self.task = asyncio.create_task(self._reader())

    async def _reader(self):
        loop = asyncio.get_event_loop()
        while self.proc and self.proc.poll() is None:
            for pipe, is_err in [(self.proc.stdout, False), (self.proc.stderr, True)]:
                try:
                    line = await loop.run_in_executor(None, pipe.readline)
                    if line: await self._broadcast(line, is_err)
                except: pass
            await asyncio.sleep(0.05)

    async def _broadcast(self, line: str, is_err: bool):
        async with self.lock:
            for ws in self.clients:
                try: await ws.send_json({"type":"output","line":line,"is_stderr":is_err})
                except: pass
        try:
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("INSERT INTO agent_output (agent_id,output,is_stderr) VALUES (?,?,?)",
                     (self.aid, line, 1 if is_err else 0))
            conn.commit(); conn.close()
        except: pass

    async def send(self, cmd: str):
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(cmd+"\n"); self.proc.stdin.flush()
            await self._broadcast(f">>> {cmd}\n", False)

    async def stop(self):
        if self.proc:
            self.proc.terminate()
            try: self.proc.wait(timeout=5)
            except: self.proc.kill()
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        async with self.lock:
            for ws in self.clients:
                try: await ws.close()
                except: pass
            self.clients.clear()

ACTIVE: Dict[int, AgentProcess] = {}

# ═════════════════════════════ FastAPI App ════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    for a in list(ACTIVE.values()): await a.stop()

app = FastAPI(lifespan=lifespan, title="Thumbtack", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# ── Pages ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(r: Request): return templates.TemplateResponse(r, "index.html")

@app.get("/project/{pid}", response_class=HTMLResponse)
async def project_page(r: Request, pid: int):
    # Pass project_id to the template
    return templates.TemplateResponse(r, "project.html")

# ── API ────────────────────────────────────────────────────────────────
@app.get("/api/projects")
async def list_projects():
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    c = conn.cursor(); c.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

@app.post("/api/projects")
async def create_project(data: dict):
    name, path = data.get("name","").strip(), data.get("path","").strip()
    if not name or not path: raise HTTPException(400, "Name and path required")
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO projects (name,path,description) VALUES (?,?,?)",
              (name, path, data.get("description")))
    conn.commit(); pid = c.lastrowid
    c.execute("SELECT * FROM projects WHERE id=?", (pid,))
    row = dict(c.fetchone()); conn.close(); return row

@app.get("/api/projects/{pid}")
async def get_project(pid: int):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id=?", (pid,)); row = c.fetchone()
    if not row: raise HTTPException(404, "Project not found")
    project = dict(row)
    c.execute("SELECT * FROM agents WHERE project_id=?", (pid,)); project["agents"] = [dict(r) for r in c.fetchall()]
    c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC", (pid,)); project["tasks"] = [dict(r) for r in c.fetchall()]
    if os.path.isdir(project["path"]):
        try: project["files"] = sorted([{"name":e.name,"is_dir":e.is_dir(),"path":e.path} for e in os.scandir(project["path"])], key=lambda x:(not x["is_dir"],x["name"].lower()))
        except PermissionError: project["files"] = []
    else: project["files"] = []
    conn.close(); return project

@app.post("/api/agents")
async def spawn_agent(data: dict):
    pid = data.get("project_id"); atype = data.get("agent_type")
    cmd = data.get("command") or None
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT path FROM projects WHERE id=?", (pid,)); row = c.fetchone()
    if not row: conn.close(); raise HTTPException(404, "Project not found")
    path = row[0]
    c.execute("INSERT INTO agents (project_id,agent_type,command,status) VALUES (?,?,?,?)",
              (pid, atype, cmd, "running")); conn.commit(); aid = c.lastrowid; conn.close()
    ap = AgentProcess(aid, atype, path, cmd)
    try: await ap.start(); ACTIVE[aid] = ap
    except Exception as e:
        conn = sqlite3.connect(DB); c = conn.cursor()
        c.execute("UPDATE agents SET status=? WHERE id=?", ("error",aid)); conn.commit(); conn.close()
        raise HTTPException(500, str(e))
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT * FROM agents WHERE id=?", (aid,)); row = dict(c.fetchone()); conn.close(); return row

@app.post("/api/agents/{aid}/command")
async def send_cmd(aid: int, data: dict):
    if aid not in ACTIVE: raise HTTPException(404, "Agent not running")
    await ACTIVE[aid].send(data.get("command","")); return {"status":"sent"}

@app.delete("/api/agents/{aid}")
async def kill_agent(aid: int):
    if aid in ACTIVE: await ACTIVE[aid].stop(); del ACTIVE[aid]
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE agents SET status=? WHERE id=?", ("stopping",aid)); conn.commit(); conn.close()
    return {"status":"killed"}

@app.get("/api/agents/{aid}/output")
async def get_output(aid: int, limit: int=100):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("SELECT * FROM agent_output WHERE agent_id=? ORDER BY created_at DESC LIMIT ?", (aid,limit))
    rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows[::-1]

@app.post("/api/projects/{pid}/tasks")
async def queue_task(pid: int, data: dict):
    cmd = data.get("command","").strip()
    if not cmd: raise HTTPException(400, "Command required")
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO tasks (project_id,command,status) VALUES (?,?,?)", (pid,cmd,"pending"))
    conn.commit(); tid = c.lastrowid
    c.execute("SELECT * FROM tasks WHERE id=?", (tid,)); row = dict(c.fetchone()); conn.close(); return row

@app.get("/api/projects/{pid}/tasks")
async def list_tasks(pid: int):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC", (pid,))
    rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

# ── WebSocket ────────────────────────────────────────────────────────
@app.websocket("/ws/agent/{aid}")
async def ws(websocket: WebSocket, aid: int):
    await websocket.accept()
    if aid not in ACTIVE:
        await websocket.send_json({"type":"error","message":"Agent not running"})
        await websocket.close(); return
    async with ACTIVE[aid].lock: ACTIVE[aid].clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if aid in ACTIVE: await ACTIVE[aid].send(data)
    except WebSocketDisconnect: pass
    finally:
        async with ACTIVE[aid].lock:
            if websocket in ACTIVE[aid].clients: ACTIVE[aid].clients.remove(websocket)

@app.get("/health")
async def health(): return {"status":"ok","agents":len(ACTIVE)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3456, reload=False)
