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


class TaskQueueRequest(BaseModel):
    task_text: str = Field(..., min_length=1)


class TaskQueueResponse(BaseModel):
    id: int
    project_id: int
    task_text: str
    status: str
    agent_id: Optional[int]
    result: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
