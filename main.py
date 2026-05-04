"""Thumbtack - Multi-Agent Orchestrator Dashboard."""
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import json
from pathlib import Path

from models import (
    ProjectCreate, ProjectResponse, SpawnAgentRequest,
    CommandRequest, AgentResponse, AgentType
)
from database import (
    init_db, create_project, list_projects, get_project, delete_project,
    create_agent, list_agents, get_agent, update_agent_status, delete_agent,
    add_command, get_command_history, add_log, get_logs
)
from agent_runner import agent_manager

app = FastAPI(title="Thumbtack", version="1.1.0")
templates = Jinja2Templates(directory="templates")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/projects", response_model=list)
async def api_list_projects():
    return list_projects()


@app.post("/api/projects")
async def api_create_project(project: ProjectCreate):
    pid = create_project(project.name, project.path, project.description or "")
    return {"id": pid, "status": "created"}


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: int):
    return get_project(project_id)


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: int):
    delete_project(project_id)
    return {"status": "deleted"}


@app.get("/api/projects/{project_id}/agents")
async def api_list_agents(project_id: int):
    return list_agents(project_id)


@app.post("/api/projects/{project_id}/agents")
async def api_spawn_agent(project_id: int, req: SpawnAgentRequest):
    agent_type = req.agent_type.value
    custom = req.custom_command or ""
    agent_id = create_agent(project_id, agent_type, custom)
    project = get_project(project_id)
    if project:
        pid = await agent_manager.spawn(agent_id, project_id, agent_type, project['path'], custom)
        if pid:
            update_agent_status(agent_id, "running", pid)
            return {"id": agent_id, "status": "running", "pid": pid}
    return {"id": agent_id, "status": "idle"}


@app.delete("/api/agents/{agent_id}")
async def api_kill_agent(agent_id: int):
    success = await agent_manager.kill(agent_id)
    if success:
        update_agent_status(agent_id, "stopped")
    return {"status": "stopped" if success else "not_found"}


@app.post("/api/agents/{agent_id}/commands")
async def api_send_command(agent_id: int, req: CommandRequest):
    add_command(agent_id, req.command)
    result = await agent_manager.send_command(agent_id, req.command)
    return {"sent": result}


@app.get("/api/agents/{agent_id}/logs")
async def api_get_logs(agent_id: int, limit: int = 500):
    return get_logs(agent_id, limit)


@app.get("/api/agents/{agent_id}/history")
async def api_get_history(agent_id: int):
    return get_command_history(agent_id)


@app.get("/api/projects/{project_id}/files")
async def api_list_files(project_id: int, path: str = ""):
    project = get_project(project_id)
    if not project:
        return {"files": [], "error": "Project not found"}
    base = Path(project['path'])
    target = base / path if path else base
    if not target.exists() or not str(target).startswith(str(base)):
        return {"files": [], "error": "Invalid path"}
    files = []
    try:
        entries = sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries[:200]:
            files.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0,
                "path": str(entry.relative_to(base))
            })
    except PermissionError:
        return {"files": [], "error": "Permission denied"}
    return {"files": files}


@app.websocket("/ws/agent/{agent_id}")
async def websocket_agent(websocket: WebSocket, agent_id: int):
    await websocket.accept()
    agent = get_agent(agent_id)
    if not agent:
        await websocket.close(code=1008)
        return

    async def send_update(stream: str, line: str):
        try:
            await websocket.send_json({"stream": stream, "line": line})
        except Exception:
            pass

    agent_manager.subscribe(agent_id, send_update)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "command" and msg.get("command"):
                    await agent_manager.send_command(agent_id, msg["command"])
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        agent_manager.unsubscribe(agent_id, send_update)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3456, log_level="info")
