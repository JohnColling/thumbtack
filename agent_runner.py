"""Thumbtack - Agent Runner.

Manages agent subprocesses with asyncio and WebSocket streaming.
"""
import asyncio
import os
import signal
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class AgentProcess:
    agent_id: int
    project_id: int
    agent_type: str
    process: asyncio.subprocess.Process
    task: asyncio.Task
    listeners: list = field(default_factory=list)
    history: list = field(default_factory=list)
    running: bool = False


class AgentManager:
    def __init__(self):
        self.agents: Dict[int, AgentProcess] = {}

    def _resolve_executable(self, agent_type: str, custom_command: str = "") -> list:
        if agent_type == "claude":
            return ["claude", "-p"]
        elif agent_type == "codex":
            return ["codex"]
        elif agent_type == "opencode":
            return ["opencode"]
        elif agent_type == "openclaw":
            return ["openclaw"]
        elif agent_type == "aider":
            return ["aider"]
        elif custom_command:
            return custom_command.split()
        return ["bash"]

    async def spawn(self, agent_id: int, project_id: int, agent_type: str, path: str, custom: str = ""):
        if agent_id in self.agents:
            return None

        cmd = self._resolve_executable(agent_type, custom)
        env = {**os.environ, "PROJECT_ROOT": path}
        pid = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=path,
                env=env
            )
            pid = proc.pid
            agent = AgentProcess(
                agent_id=agent_id,
                project_id=project_id,
                agent_type=agent_type,
                process=proc,
                task=None,
                running=True
            )
            self.agents[agent_id] = agent
            agent.task = asyncio.create_task(self._stream(agent))
            return pid
        except Exception as e:
            return None

    async def _stream(self, agent: AgentProcess):
        loop = asyncio.get_event_loop()
        stdout_task = loop.create_task(self._read_stream(agent, agent.process.stdout, "stdout"))
        stderr_task = loop.create_task(self._read_stream(agent, agent.process.stderr, "stderr"))
        await asyncio.gather(stdout_task, stderr_task)
        agent.running = False
        await agent.process.wait()
        for cb in list(agent.listeners):
            try:
                cb("system", f"Agent {agent.agent_id} exited with code {agent.process.returncode}")
            except Exception:
                pass

    async def _read_stream(self, agent: AgentProcess, stream, stream_name: str):
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                agent.history.append((stream_name, text))
                for cb in list(agent.listeners):
                    try:
                        cb(stream_name, text)
                    except Exception:
                        pass
        except Exception:
            pass

    def subscribe(self, agent_id: int, callback: Callable[[str, str], None]):
        agent = self.agents.get(agent_id)
        if agent:
            agent.listeners.append(callback)

    def unsubscribe(self, agent_id: int, callback: Callable[[str, str], None]):
        agent = self.agents.get(agent_id)
        if agent and callback in agent.listeners:
            agent.listeners.remove(callback)

    async def send_command(self, agent_id: int, command: str):
        agent = self.agents.get(agent_id)
        if agent and agent.process and agent.process.stdin:
            agent.process.stdin.write((command + "\n").encode())
            await agent.process.stdin.drain()
            return True
        return False

    async def kill(self, agent_id: int, force: bool = False):
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        proc = agent.process
        if force and proc.pid:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.kill()
        agent.running = False
        if agent.task and not agent.task.done():
            agent.task.cancel()
            try:
                await agent.task
            except asyncio.CancelledError:
                pass
        del self.agents[agent_id]
        return True

    def get_status(self, agent_id: int) -> Optional[dict]:
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        return {
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "pid": agent.process.pid,
            "running": agent.running,
            "history_length": len(agent.history)
        }

    def list_by_project(self, project_id: int):
        return [a for a in self.agents.values() if a.project_id == project_id]


agent_manager = AgentManager()
