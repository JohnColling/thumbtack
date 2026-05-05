"""Thumbtack – Multi-agent orchestration Dashboard.

File: database.py
SQLite database layer for Thumbtack orchestrator.
"""
import sqlite3
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional, Dict, Any
from pathlib import Path

DB_PATH = Path(__file__).parent / "thumbtack.db"
TZ = ZoneInfo("Australia/Brisbane")

def now_aest() -> str:
    """Return current AEST (UTC+10) timestamp as readable string."""
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        path TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        agent_type TEXT NOT NULL,
        custom_command TEXT DEFAULT '',
        pid INTEGER,
        status TEXT DEFAULT 'idle',
        created_at TEXT DEFAULT '',
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS command_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        created_at TEXT DEFAULT '',
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        stream TEXT NOT NULL,
        line TEXT NOT NULL,
        created_at TEXT DEFAULT '',
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        priority INTEGER DEFAULT 3,
        status TEXT DEFAULT 'pending',
        parent_task_id INTEGER,
        assigned_agent_id INTEGER,
        assigned_agent_type TEXT DEFAULT 'claude',
        command TEXT DEFAULT '',
        result TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        planned_at TIMESTAMP,
        approved_at TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id),
        FOREIGN KEY (parent_task_id) REFERENCES tasks(id),
        FOREIGN KEY (assigned_agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT '',
        level TEXT NOT NULL DEFAULT 'INFO',
        message TEXT NOT NULL,
        task_id INTEGER,
        agent_id INTEGER,
        project_id INTEGER,
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (agent_id) REFERENCES agents(id),
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS github_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        username TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        default_branch TEXT NOT NULL DEFAULT 'main',
        updated_at TEXT DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_output (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        output TEXT, is_stderr INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_outputs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        agent_id INTEGER,
        output TEXT NOT NULL,
        is_stderr INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (task_id) REFERENCES tasks(id),
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    conn.commit()
    conn.close()


def create_project(name: str, path: str, description: str = "") -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, path, description) VALUES (?, ?, ?)",
        (name, path, description)
    )
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def list_projects() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_project(project_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def create_agent(project_id: int, agent_type: str, custom_command: str = "", pid: Optional[int] = None) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (project_id, agent_type, custom_command, pid, status) VALUES (?, ?, ?, ?, ?)",
        (project_id, agent_type, custom_command, pid, "running" if pid else "idle")
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id


def list_agents(project_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if project_id:
        cursor.execute("SELECT * FROM agents WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    else:
        cursor.execute("SELECT * FROM agents ORDER BY created_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_agent(agent_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_agent_status(agent_id: int, status: str, pid: Optional[int] = None) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    if pid is not None:
        cursor.execute("UPDATE agents SET status = ?, pid = ? WHERE id = ?", (status, pid, agent_id))
    else:
        cursor.execute("UPDATE agents SET status = ? WHERE id = ?", (status, agent_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_agent(agent_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def add_command(agent_id: int, command: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO command_history (agent_id, command) VALUES (?, ?)",
        (agent_id, command)
    )
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return cmd_id


def get_command_history(agent_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM command_history WHERE agent_id = ? ORDER BY created_at DESC", (agent_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def add_log(agent_id: int, stream: str, line: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (agent_id, stream, line) VALUES (?, ?, ?)",
        (agent_id, stream, line)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_logs(agent_id: int, limit: int = 1000) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM logs WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def create_task(project_id: int, title: str, description: str = "", priority: int = 3) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, priority, status) VALUES (?, ?, ?, ?, ?)",
        (project_id, title, description, priority, "pending")
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def list_tasks(project_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_task_status(task_id: int, status: str, result: str = "", agent_id: Optional[int] = None) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    now = now_aest()
    if status == "planning":
        cursor.execute("UPDATE tasks SET status = ?, planned_at = ? WHERE id = ?", (status, now, task_id))
    elif status == "approved":
        cursor.execute("UPDATE tasks SET status = ?, approved_at = ? WHERE id = ?", (status, now, task_id))
    elif status == "running":
        cursor.execute("UPDATE tasks SET status = ?, assigned_agent_id = ?, started_at = ? WHERE id = ?",
                       (status, agent_id, now, task_id))
    elif status in ("done", "failed"):
        cursor.execute("UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?",
                       (status, result, now, task_id))
    else:
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_task(task_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def create_subtasks(parent_task_id: int, project_id: int, subtasks: List[dict]) -> List[int]:
    """Create subtask rows from a decomposition plan. Returns list of new task IDs."""
    ids = []
    conn = get_db()
    cursor = conn.cursor()
    for st in subtasks:
        cursor.execute(
            "INSERT INTO tasks (project_id, parent_task_id, title, description, priority, status) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, parent_task_id, st["title"], st.get("description", ""), st.get("priority", 3), "queued")
        )
        ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    return ids


def get_subtasks(parent_task_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY priority, id", (parent_task_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_pending_tasks() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority, created_at")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_queued_tasks() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'queued' ORDER BY priority, created_at")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_running_tasks() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'running' ORDER BY created_at")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_github_settings() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM github_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def save_github_settings(username: str, email: str, token: Optional[str] = None, default_branch: str = "main") -> bool:
    conn = get_db()
    cursor = conn.cursor()
    now = now_aest()
    cursor.execute("SELECT token FROM github_settings WHERE id = 1")
    existing = cursor.fetchone()
    if token is None and existing:
        token = existing[0]           # preserve existing when omitted
    elif token is None:
        token = ""
    if existing:
        cursor.execute(
            "UPDATE github_settings SET username = ?, email = ?, token = ?, default_branch = ?, updated_at = ? WHERE id = 1",
            (username, email, token, default_branch, now)
        )
    else:
        cursor.execute(
            "INSERT INTO github_settings (id, username, email, token, default_branch, updated_at) VALUES (1, ?, ?, ?, ?, ?)",
            (username, email, token, default_branch, now)
        )
    conn.commit()
    conn.close()
    return True


def delete_github_settings() -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM github_settings WHERE id = 1")
    conn.commit()
    conn.close()
    return True

def add_agent_log(level: str, message: str, task_id: int = None, agent_id: int = None, project_id: int = None) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agent_log (timestamp, level, message, task_id, agent_id, project_id) VALUES (?, ?, ?, ?, ?, ?)",
        (now_aest(), level, message, task_id, agent_id, project_id)
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_agent_logs(limit: int = 100, project_id: int = None, level: str = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if project_id and level:
        cursor.execute(
            "SELECT * FROM agent_log WHERE project_id = ? AND level = ? ORDER BY timestamp DESC LIMIT ?",
            (project_id, level, limit)
        )
    elif project_id:
        cursor.execute(
            "SELECT * FROM agent_log WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?",
            (project_id, limit)
        )
    elif level:
        cursor.execute(
            "SELECT * FROM agent_log WHERE level = ? ORDER BY timestamp DESC LIMIT ?",
            (level, limit)
        )
    else:
        cursor.execute(
            "SELECT * FROM agent_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_agent_logs(minutes: int = 60) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    from datetime import datetime, timedelta
    now = datetime.fromisoformat(now_aest())
    cutoff = (now - timedelta(minutes=minutes)).isoformat()
    cursor.execute(
        "SELECT * FROM agent_log WHERE timestamp > ? ORDER BY timestamp DESC",
        (cutoff,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def add_task_output(task_id: int, output: str, agent_id: int = None, is_stderr: bool = False) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO task_outputs (task_id, agent_id, output, is_stderr) VALUES (?, ?, ?, ?)",
        (task_id, agent_id, output, 1 if is_stderr else 0)
    )
    oid = cursor.lastrowid
    conn.commit()
    conn.close()
    return oid


def get_task_outputs(task_id: int, limit: int = 500) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_outputs WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
        (task_id, limit)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows[::-1]  # chronological


def get_orphaned_queued_tasks() -> List[Dict[str, Any]]:
    """Return queued tasks whose parent is approved (ready to run)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.* FROM tasks t
        LEFT JOIN tasks parent ON t.parent_task_id = parent.id
        WHERE t.status = 'queued'
        AND (t.parent_task_id IS NULL OR parent.status = 'approved')
        ORDER BY t.priority, t.created_at
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
