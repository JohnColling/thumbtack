"""
ThumbTack External API — outside services interact with the orchestrator.
GET endpoints for state reading; POST endpoints for task creation, dispatch,
agent spawning, and event emission. All protected by X-Webhook-Secret.
"""
import os, json
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from database import (
    get_db, list_projects, get_project as db_get_project,
    list_agents, get_agent as db_get_agent,
    list_tasks as db_list_tasks, get_task as db_get_task,
    create_task as db_create_task, update_task_status,
    get_queued_tasks, get_running_tasks, get_pending_tasks,
    add_agent_log, record_webhook_delivery,
    get_agent_logs,
)
from worker_pool import get_pool

WEBHOOK_SECRET = os.getenv("THUMBTACK_WEBHOOK_SECRET", "")

router = APIRouter()

def _check_secret(x_webhook_secret: str):
    if not WEBHOOK_SECRET:
        raise HTTPException(500, "Webhook secret not configured on server")
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret")

# ─── Read: Projects ──────────────────────────────────────────────────────
@router.get("/projects")
async def ext_list_projects(x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    return {"projects": list_projects()}

@router.get("/projects/{pid}")
async def ext_get_project(pid: int, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    proj = db_get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    proj["agents"] = list_agents(pid)
    proj["tasks"] = db_list_tasks(pid)
    return {"project": proj}

# ─── Read: Agents ────────────────────────────────────────────────────────
@router.get("/agents")
async def ext_list_agents(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    x_webhook_secret: str = Header(default="")
):
    _check_secret(x_webhook_secret)
    rows = list_agents(project_id)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {"agents": rows}

@router.get("/agents/{aid}")
async def ext_get_agent(aid: int, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    row = db_get_agent(aid)
    if not row:
        raise HTTPException(404, "Agent not found")
    return {"agent": row}

# ─── Read: Tasks ─────────────────────────────────────────────────────────
@router.get("/tasks")
async def ext_list_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    x_webhook_secret: str = Header(default="")
):
    _check_secret(x_webhook_secret)
    if project_id:
        rows = db_list_tasks(project_id)
    else:
        # cross-project list
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {"tasks": rows}

@router.get("/tasks/{tid}")
async def ext_get_task(tid: int, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    row = db_get_task(tid)
    if not row:
        raise HTTPException(404, "Task not found")
    row["subtasks"] = []
    if row.get("parent_task_id") is None:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY priority, id", (tid,))
        row["subtasks"] = [dict(r) for r in cur.fetchall()]
        conn.close()
    return {"task": row}

# ─── Read: Orchestrator ──────────────────────────────────────────────────
@router.get("/orchestrator/status")
async def ext_orchestrator_status(x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    return {
        "queued": len(get_queued_tasks()),
        "running": len(get_running_tasks()),
        "pending": len(get_pending_tasks()),
    }

@router.get("/logs")
async def ext_logs(
    limit: int = Query(default=50, le=500),
    project_id: Optional[int] = None,
    level: Optional[str] = None,
    x_webhook_secret: str = Header(default="")
):
    _check_secret(x_webhook_secret)
    rows = get_agent_logs(limit=limit, project_id=project_id, level=level)
    return {"logs": rows}

# ─── Write: Tasks ────────────────────────────────────────────────────────
class CreateTaskRequest(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = ""
    priority: int = 3
    auto_approve: bool = False

@router.post("/tasks")
async def ext_create_task(data: CreateTaskRequest, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    proj = db_get_project(data.project_id)
    if not proj:
        record_webhook_delivery("create_task", project_id=data.project_id, payload=data.json(), result="project_not_found")
        raise HTTPException(404, "Project not found")
    title = data.title.strip()
    if not title:
        raise HTTPException(400, "title required")
    tid = db_create_task(data.project_id, title, data.description or "", data.priority)
    if data.auto_approve:
        update_task_status(tid, "approved")
    add_agent_log("EXTERNAL_TASK_CREATED", f"External API created task #{tid}: {title}", task_id=tid, project_id=data.project_id)
    record_webhook_delivery("create_task", project_id=data.project_id, task_id=tid, payload=data.json(), result="created")
    return {"status": "created", "task_id": tid, "approved": data.auto_approve}

class DispatchRequest(BaseModel):
    project_id: int
    task_id: int

@router.post("/tasks/{tid}/dispatch")
async def ext_dispatch_task(tid: int, data: DispatchRequest, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    task = db_get_task(tid)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["project_id"] != data.project_id:
        raise HTTPException(400, "Task does not belong to project")
    if task["status"] == "queued":
        pool = get_pool()
        await pool.tick()
        add_agent_log("EXTERNAL_TASK_DISPATCHED", f"External API dispatched task #{tid}", task_id=tid, project_id=data.project_id)
        return {"status": "dispatched", "task_id": tid}
    elif task["status"] == "pending":
        update_task_status(tid, "approved")
        pool = get_pool()
        await pool.tick()
        add_agent_log("EXTERNAL_TASK_DISPATCHED", f"External API approved+dispatched task #{tid}", task_id=tid, project_id=data.project_id)
        return {"status": "approved_and_dispatched", "task_id": tid}
    else:
        raise HTTPException(400, f"Task status is '{task['status']}', cannot dispatch")

# ─── Write: Events ───────────────────────────────────────────────────────
class EventRequest(BaseModel):
    level: str = "INFO"          # INFO | WARNING | ERROR | SYSTEM
    message: str
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    agent_id: Optional[int] = None

@router.post("/events")
async def ext_emit_event(data: EventRequest, x_webhook_secret: str = Header(default="")):
    _check_secret(x_webhook_secret)
    lid = add_agent_log(
        data.level.upper(),
        data.message,
        project_id=data.project_id,
        task_id=data.task_id,
        agent_id=data.agent_id,
    )
    return {"status": "logged", "log_id": lid}
