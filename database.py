"""Thumbtack – Multi-agent orchestration Dashboard.

File: database.py
SQLite database layer for Thumbtack orchestrator.
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

DB_PATH = Path(__file__).parent / "thumbtack.db"


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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS command_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        stream TEXT NOT NULL,
        line TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        agent_id INTEGER,
        command TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        result TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id),
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS github_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        username TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        default_branch TEXT NOT NULL DEFAULT 'main',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def add_task(project_id: int, command: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (project_id, command) VALUES (?, ?)",
        (project_id, command)
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
    now = datetime.now().isoformat()
    if status == "running":
        cursor.execute("UPDATE tasks SET status = ?, agent_id = ?, started_at = ? WHERE id = ?",
                       (status, agent_id, now, task_id))
    elif status in ("completed", "failed"):
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
    now  = datetime.now().isoformat()
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
