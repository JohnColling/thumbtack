"""ThumbTack Phase 3 — Agent Worker Pool.

Task-bound agent subprocesses with isolated workspaces, streaming output,
and automatic lifecycle management (running → done/failed).
"""
import asyncio
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

from database import (
    DB_PATH, now_aest, update_task_status, add_agent_log,
    get_queued_tasks, get_running_tasks, get_project, create_agent,
    add_task_output
)

# ── Config ────────────────────────────────────────────────────────────────
MAX_WORKERS = 1          # Start conservative; bump when stable
DISPATCH_INTERVAL = 5    # seconds between queue polls
AGENT_EXECS = {
    "claude":   ["/home/administrator/.local/bin/claude", "/usr/local/bin/claude"],
    "codex":    ["/usr/local/bin/codex"],
    "opencode": ["/usr/local/bin/opencode"],
    "aider":    ["/usr/local/bin/aider", "/home/administrator/.local/bin/aider"],
}


def _resolve_cmd(agent_type: str, custom_command: str = "") -> list:
    """Return shell-command list for the given agent type.

    `custom_command` is a *prompt/description* to be piped to the agent's stdin,
    NOT a shell command.  The return list is the executable + args ready for
    subprocess.Popen.
    """
    for path in AGENT_EXECS.get(agent_type, []):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return [path, "-p"]          # every CLI we use supports -p
    # If the custom_command looks like a shell command (starts with known binaries),
    # allow explicit override.
    stripped = (custom_command or "").strip()
    if stripped.startswith(("python ", "bash ", "sh ", "python3 ", "node ")):
        return stripped.split()
    return ["python", "-c",
            f"print('ThumbTack: {agent_type} placeholder for task')"]


# ── Task-bound Agent ──────────────────────────────────────────────────────
class TaskAgent:
    """A single agent subprocess tied to one task, running in an isolated copy
    of the project directory.
    """

    def __init__(self, task_id: int, project_id: int, agent_type: str,
                 project_path: str, custom_command: str = ""):
        self.task_id   = task_id
        self.project_id = project_id
        self.agent_type = agent_type
        self.project_path = os.path.abspath(project_path)
        self.custom_command = custom_command

        self.agent_id: Optional[int] = None
        self.workspace: Optional[str] = None
        self.proc: Optional[subprocess.Popen] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._clients: list = []          # WebSocket clients
        self._alive = False

    # ── workspace ─────────────────────────────────────────────────────────
    async def _prepare_workspace(self) -> str:
        """Create a temp copy of the project.  Returns workspace path."""
        ws = tempfile.mkdtemp(prefix=f"tt_task_{self.task_id}_")
        git_dir = os.path.join(self.project_path, ".git")

        if os.path.isdir(git_dir):
            # shallow clone preserves branch + remote info quickly
            r = subprocess.run(
                ["git", "clone", "--depth=1", "--", self.project_path, ws],
                capture_output=True, text=True
            )
            if r.returncode != 0:
                # fallback: plain copy
                shutil.copytree(self.project_path, ws, dirs_exist_ok=True)
        else:
            shutil.copytree(self.project_path, ws, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".git"))
        self.workspace = ws
        return ws

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def start(self) -> "TaskAgent":
        """Prepare workspace, spawn subprocess, feed prompt, mark task running."""
        ws = await self._prepare_workspace()
        cmd = _resolve_cmd(self.agent_type, self.custom_command)

        env = {**os.environ, "PROJECT_ROOT": ws, "THUMBTACK_TASK_ID": str(self.task_id)}
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ws,
            env=env,
            text=True,
            bufsize=1,
        )
        self._alive = True

        # Feed the task prompt to stdin and close it so the CLI sees EOF
        if self.proc and self.proc.stdin:
            prompt_text = f"Task: {self.task_id}\nPrompt: {self.custom_command or 'Execute this task'}\n"
            try:
                self.proc.stdin.write(prompt_text)
                self.proc.stdin.flush()
                self.proc.stdin.close()
            except BrokenPipeError:
                pass  # process already exited

        # DB agent row (status=running)
        self.agent_id = create_agent(
            self.project_id, self.agent_type,
            custom_command=self.custom_command or " ".join(cmd),
            pid=self.proc.pid
        )
        update_task_status(self.task_id, "running",
                           agent_id=self.agent_id)
        add_agent_log(
            "AGENT_START",
            f"Task #{self.task_id} → {self.agent_type} agent #{self.agent_id}",
            task_id=self.task_id, project_id=self.project_id
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def stop(self):
        """Terminate subprocess, cancel reader, nuke workspace."""
        self._alive = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.workspace and os.path.isdir(self.workspace):
            try:
                shutil.rmtree(self.workspace)
            except Exception:
                pass
        add_agent_log(
            "AGENT_STOP",
            f"Task #{self.task_id} agent stopped",
            task_id=self.task_id, project_id=self.project_id
        )

    # ── I/O ─────────────────────────────────────────────────────────────────
    async def _read_loop(self):
        """Pump stdout/stderr → WebSocket clients + agent_output table."""
        loop = asyncio.get_event_loop()
        try:
            while self._alive and self.proc and self.proc.poll() is None:
                for pipe, is_err in [(self.proc.stdout, False),
                                      (self.proc.stderr, True)]:
                    try:
                        line = await loop.run_in_executor(None, pipe.readline)
                        if line:
                            await self._emit(line.rstrip("\n"), is_err)
                    except Exception:
                        pass
                await asyncio.sleep(0.05)

            # flush remaining
            if self.proc:
                for pipe in [self.proc.stdout, self.proc.stderr]:
                    try:
                        rem = pipe.read()
                        if rem:
                            for ln in rem.splitlines():
                                await self._emit(ln, pipe is self.proc.stderr)
                    except Exception:
                        pass

            # finalize
            code = self.proc.returncode if self.proc else -1
            await self._emit(f"[agent exited: code {code}]", False)
            status = "done" if code == 0 else "failed"
            result = f"Exit code {code}" if code != 0 else "Completed"
            update_task_status(self.task_id, status, result,
                              agent_id=self.agent_id)
            add_agent_log(
                "TASK_FINISH",
                f"Task #{self.task_id} → {status} ({result})",
                task_id=self.task_id, agent_id=self.agent_id,
                project_id=self.project_id
            )

        except asyncio.CancelledError:
            pass
        finally:
            self._alive = False
            # cleanup workspace after a short breath
            if self.workspace and os.path.isdir(self.workspace):
                try:
                    shutil.rmtree(self.workspace)
                except Exception:
                    pass

    async def _emit(self, line: str, is_err: bool):
        """Broadcast to WebSockets, agent_output, and task_output."""
        stream = "stderr" if is_err else "stdout"
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json({"stream": stream, "data": line})
            except Exception:
                dead.append(ws)
        for d in dead:
            if d in self._clients:
                self._clients.remove(d)

        # persist to agent_output (legacy) and task_outputs (Phase 3)
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute(
            "INSERT INTO agent_output (agent_id, output, is_stderr) VALUES (?,?,?)",
            (self.agent_id, line, 1 if is_err else 0)
        )
        c.execute(
            "INSERT INTO task_outputs (task_id, agent_id, output, is_stderr) VALUES (?,?,?,?)",
            (self.task_id, self.agent_id, line, 1 if is_err else 0)
        )
        conn.commit()
        conn.close()

    async def send_cmd(self, text: str):
        """Push a command line to the agent's stdin."""
        if self.proc and self.proc.stdin:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
            await self._emit(">>> " + text, False)

    # ── WebSocket plumbing ────────────────────────────────────────────────
    def register_ws(self, ws):   self._clients.append(ws)
    def unregister_ws(self, ws):
        if ws in self._clients:
            self._clients.remove(ws)


# ── Worker Pool ───────────────────────────────────────────────────────────
class WorkerPool:
    """Consumes queued tasks and dispatches TaskAgents up to max_workers."""

    def __init__(self, max_workers: int = MAX_WORKERS):
        self.max_workers = max_workers
        self._agents: Dict[int, TaskAgent] = {}   # task_id → TaskAgent
        self._dispatch_loops: Dict[int, asyncio.Task] = {}
        self._running = False

    async def start(self):
        self._running = True
        add_agent_log("SYSTEM", "WorkerPool armed")

    async def stop(self):
        self._running = False
        # stop every running agent
        for agent in list(self._agents.values()):
            await agent.stop()
        self._agents.clear()
        add_agent_log("SYSTEM", "WorkerPool stopped")

    async def tick(self):
        """Single dispatch attempt — called by heartbeat loop."""
        if not self._running:
            return
        running = get_running_tasks()
        queued   = get_queued_tasks()
        vacancy = self.max_workers - len(running)
        if vacancy <= 0 or not queued:
            return

        task = queued[0]
        task_id = task["id"]
        project_id = task["project_id"]

        proj = get_project(project_id)
        if not proj:
            update_task_status(task_id, "failed", "Project not found")
            add_agent_log("TASK_ERROR", f"Task #{task_id} orphan — project missing",
                         task_id=task_id, project_id=project_id)
            return

        agent_type = task.get("assigned_agent_type", "claude")

        # Prevent double-dispatch
        if task_id in self._agents:
            return

        agent = TaskAgent(
            task_id=task_id,
            project_id=project_id,
            agent_type=agent_type,
            project_path=proj["path"],
            custom_command=task.get("command", "")
        )

        try:
            await agent.start()
            self._agents[task_id] = agent
        except Exception as e:
            self._agents.pop(task_id, None)
            update_task_status(task_id, "failed", str(e)[:500])
            add_agent_log("AGENT_ERROR", f"Task #{task_id} spawn failed: {e}",
                         task_id=task_id, project_id=project_id)

    def get_agent(self, task_id: int) -> Optional[TaskAgent]:
        return self._agents.get(task_id)

    async def stop_task(self, task_id: int):
        agent = self._agents.pop(task_id, None)
        if agent:
            await agent.stop()
            update_task_status(task_id, "failed", "Stopped by user")


# ── Global singleton ──────────────────────────────────────────────────────
_pool: Optional[WorkerPool] = None

def get_pool() -> WorkerPool:
    global _pool
    if _pool is None:
        _pool = WorkerPool()
    return _pool

async def start_pool():
    await get_pool().start()

async def stop_pool():
    global _pool
    if _pool:
        await _pool.stop()
        _pool = None
