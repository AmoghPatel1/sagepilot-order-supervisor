from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Supervisor
from app.schemas import SupervisorCreate, SupervisorResponse
from typing import List

router = APIRouter(prefix="/api/supervisors", tags=["supervisors"])

@router.post("", response_model=SupervisorResponse)
def create_supervisor(data: SupervisorCreate, db: Session = Depends(get_db)):
    supervisor = Supervisor(**data.dict(exclude_none=True))
    db.add(supervisor)
    db.commit()
    db.refresh(supervisor)
    return supervisor

@router.get("", response_model=List[SupervisorResponse])
def list_supervisors(db: Session = Depends(get_db)):
    return db.query(Supervisor).all()

@router.get("/{supervisor_id}", response_model=SupervisorResponse)
def get_supervisor(supervisor_id: str, db: Session = Depends(get_db)):
    supervisor = db.query(Supervisor).filter(Supervisor.id == supervisor_id).first()
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    return supervisor