"""ThumbTack ↔ Hermes Agent Bridge

When a task is dispatched with agent_type="hermes", instead of spawning a
local subprocess we hand the task to a running Hermes instance and poll for
results.  Hermes agents run autonomously via the hermes-agent CLI.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from database import (
    add_agent_log, add_task_output, update_task_status,
    get_db
)

# ── Config ─────────────────────────────────────────────────────────────
HERMES_BINARY = os.environ.get("HERMES_BINARY", "hermes")
# Thumbtack task files are written here for Hermes to pick up
HERMES_TASK_DIR = Path(os.environ.get("HERMES_TASK_DIR", "/tmp/thumbtack_hermes_tasks"))

# How long to wait before deciding Hermes is offline for a task
HERMES_TIMEOUT = int(os.environ.get("HERMES_TIMEOUT", "600"))  # 10 minutes


# ── Hermes Bridge ────────────────────────────────────────────────────────

class HermesBridge:
    """Manages task dispatch to Hermes agents.

    Design:
    - Each task gets a unique .json descriptor written to HERMES_TASK_DIR/
    - Hermes (via cron or daemon) polls this directory for new tasks
    - When done, Hermes writes a result.json back
    - ThumbTack polls the result file
    """

    def __init__(self, task_dir: Optional[Path] = None):
        self.task_dir = task_dir or HERMES_TASK_DIR
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self._running: Dict[int, asyncio.Task] = {}
        self._ws_clients: List = []

    async def dispatch(self, task_id: int, project_id: int, prompt: str,
                       context: Optional[dict] = None) -> bool:
        """Write task descriptor and start polling for results."""
        descriptor = {
            "task_id": task_id,
            "project_id": project_id,
            "prompt": prompt,
            "context": context or {},
            "status": "pending",
            "created_at": time.time(),
        }
        task_file = self.task_dir / f"task_{task_id}.json"
        task_file.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")

        add_agent_log(
            "HERMES_DISPATCH",
            f"Task #{task_id} dispatched to Hermes — wrote {task_file}",
            task_id=task_id, project_id=project_id
        )

        # Start polling for result
        poll = asyncio.create_task(self._poll_result(task_id, project_id))
        self._running[task_id] = poll
        return True

    async def _poll_result(self, task_id: int, project_id: int):
        """Poll for result.json until found or timeout."""
        result_file = self.task_dir / f"result_{task_id}.json"
        task_file   = self.task_dir / f"task_{task_id}.json"
        deadline    = time.time() + HERMES_TIMEOUT
        last_status = "running"

        try:
            while time.time() < deadline:
                if result_file.exists():
                    try:
                        data = json.loads(result_file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        await asyncio.sleep(2)
                        continue

                    status   = data.get("status", "done")
                    result   = data.get("result", "")
                    stdout   = data.get("stdout", "")
                    stderr   = data.get("stderr", "")
                    metadata = data.get("metadata", {})

                    # Save outputs (if any)
                    for line in stdout.splitlines():
                        if line.strip():
                            add_task_output(task_id, line, is_stderr=False)
                    for line in stderr.splitlines():
                        if line.strip():
                            add_task_output(task_id, line, is_stderr=True)

                    # Update DB
                    if status == "done":
                        update_task_status(task_id, "done", result=result)
                        last_status = "done"
                    elif status == "failed":
                        update_task_status(task_id, "failed", result=result)
                        last_status = "failed"
                    else:
                        update_task_status(task_id, "running")

                    # Token usage from Hermes (if reported)
                    usage = metadata.get("usage", {})
                    if usage:
                        from database import add_token_usage
                        total_t = usage.get("total_tokens")
                        if total_t is None:
                            total_t = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                        add_token_usage(
                            session_id=f"hermes_task_{task_id}",
                            project_id=project_id,
                            task_id=task_id,
                            model=usage.get("model", "hermes"),
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            total_tokens=total_t,
                            cost=usage.get("cost_usd", 0.0),
                        )

                    add_agent_log(
                        f"HERMES_{status.upper()}",
                        f"Task #{task_id} Hermes result received — {result_file}",
                        task_id=task_id, project_id=project_id
                    )

                    # Cleanup descriptors
                    try:
                        result_file.unlink()
                        if task_file.exists():
                            task_file.unlink()
                    except Exception:
                        pass

                    # Notify WebSocket clients
                    await self._broadcast({
                        "type": "task_complete",
                        "task_id": task_id,
                        "status": status,
                        "result": result,
                    })
                    return

                # Send a heartbeat update
                await self._broadcast({
                    "type": "task_progress",
                    "task_id": task_id,
                    "status": last_status,
                    "message": f"Waiting for Hermes result…",
                })
                await asyncio.sleep(3)

            # Timeout
            update_task_status(task_id, "failed", result="Hermes: timed out waiting for result")
            add_agent_log(
                "HERMES_TIMEOUT",
                f"Task #{task_id} timed out waiting for Hermes result",
                task_id=task_id, project_id=project_id
            )

        except asyncio.CancelledError:
            # Task was cancelled (e.g. user stopped the agent)
            update_task_status(task_id, "failed", result="Hermes: task cancelled")
            raise

        finally:
            if task_id in self._running:
                del self._running[task_id]

    async def _broadcast(self, message: dict):
        """Push update to any connected WebSocket clients."""
        dead = []
        for ws in list(self._ws_clients):
            try:
                import fastapi.websockets
                if hasattr(ws, "send_json"):
                    await ws.send_json(message)
                elif hasattr(ws, "send_text"):
                    await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for d in dead:
            if d in self._ws_clients:
                self._ws_clients.remove(d)

    def register_WS(self, ws):
        """Register a WebSocket client for live progress updates."""
        if ws not in self._ws_clients:
            self._ws_clients.append(ws)

    def unregister_WS(self, ws):
        """Remove a WebSocket client."""
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def cancel(self, task_id: int) -> bool:
        """Cancel polling for a task."""
        if task_id in self._running:
            self._running[task_id].cancel()
            try:
                await self._running[task_id]
            except asyncio.CancelledError:
                pass
            del self._running[task_id]
            return True
        return False

    def get_pending_tasks(self) -> List[dict]:
        """List any .json tasks still waiting for Hermes."""
        tasks = []
        for f in self.task_dir.glob("task_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tasks.append(data)
            except Exception:
                pass
        return tasks


# ── Singleton ────────────────────────────────────────────────────────────
_bridge: Optional[HermesBridge] = None

def get_hermes_bridge() -> HermesBridge:
    global _bridge
    if _bridge is None:
        _bridge = HermesBridge()
    return _bridge
