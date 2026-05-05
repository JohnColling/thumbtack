from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AgentType(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    AIDER = "aider"
    CUSTOM = "custom"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    path: str = Field(..., min_length=1)
    description: Optional[str] = Field(default="")


class ProjectResponse(BaseModel):
    id: int
    name: str
    path: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SpawnAgentRequest(BaseModel):
    project_id: int
    agent_type: AgentType
    custom_command: Optional[str] = ""


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1)


class AgentResponse(BaseModel):
    id: int
    project_id: int
    agent_type: str
    custom_command: Optional[str]
    pid: Optional[int]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class CommandHistoryResponse(BaseModel):
    id: int
    agent_id: int
    command: str
    created_at: datetime

    class Config:
        from_attributes = True


class LogEntryResponse(BaseModel):
    id: int
    agent_id: int
    stream: str
    line: str
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    priority: int = Field(default=3, ge=1, le=5)


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    priority: int
    status: str
    parent_task_id: Optional[int] = None
    assigned_agent_id: Optional[int] = None
    result: str = ""
    created_at: Optional[str] = None
    planned_at: Optional[str] = None
    approved_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DecomposeRequest(BaseModel):
    subtasks: list


class TaskQueueRequest(BaseModel):
    task_text: str = Field(..., min_length=1)
