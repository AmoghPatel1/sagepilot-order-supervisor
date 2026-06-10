from sqlalchemy import Column, String, Text, Integer, ARRAY, TIMESTAMP, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Supervisor(Base):
    __tablename__ = "supervisors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    base_instruction = Column(Text, nullable=False)
    available_actions = Column(ARRAY(Text), default=[
        'message_fulfillment_team',
        'message_payments_team',
        'message_logistics_team',
        'message_customer',
        'create_internal_note'
    ])
    default_wake_interval_minutes = Column(Integer, default=30)
    wake_aggressiveness = Column(Text, default='normal')
    model = Column(Text, default='claude-haiku-4-5-20251001')
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supervisor_id = Column(UUID(as_uuid=True), nullable=False)
    order_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='running')
    wake_at = Column(TIMESTAMP(timezone=True), nullable=True)
    state_summary = Column(Text, default='')
    additional_instructions = Column(Text, default='')
    final_output = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), nullable=False)
    entry_type = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())