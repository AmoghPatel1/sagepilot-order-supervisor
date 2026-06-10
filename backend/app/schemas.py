from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid

# Supervisor schemas
class SupervisorCreate(BaseModel):
    name: str
    base_instruction: str
    available_actions: Optional[List[str]] = None
    default_wake_interval_minutes: Optional[int] = 30
    wake_aggressiveness: Optional[str] = 'normal'
    model: Optional[str] = 'claude-haiku-4-5-20251001'

class SupervisorResponse(BaseModel):
    id: uuid.UUID
    name: str
    base_instruction: str
    available_actions: List[str]
    default_wake_interval_minutes: int
    wake_aggressiveness: str
    model: str
    created_at: datetime

    class Config:
        from_attributes = True

# Run schemas
class RunCreate(BaseModel):
    supervisor_id: uuid.UUID
    order_id: str
    additional_instructions: Optional[str] = ''

class RunResponse(BaseModel):
    id: uuid.UUID
    supervisor_id: uuid.UUID
    order_id: str
    status: str
    wake_at: Optional[datetime]
    state_summary: str
    additional_instructions: str
    final_output: Optional[Any]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

# Event injection schema
class EventInject(BaseModel):
    event_type: str
    payload: Optional[dict] = {}

# Instruction injection schema
class InstructionAdd(BaseModel):
    instruction: str

# Activity log schema
class ActivityLogResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    entry_type: str
    payload: Any
    created_at: datetime

    class Config:
        from_attributes = True