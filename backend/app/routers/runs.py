import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ActivityLog, Run, Supervisor
from app.schemas import (
    ActivityLogResponse,
    EventInject,
    InstructionAdd,
    RunCreate,
    RunResponse,
)
from app.services.agent import run_agent
from app.services.classifier import is_urgent

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunResponse)
def create_run(
    data: RunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    supervisor = (
        db.query(Supervisor).filter(Supervisor.id == data.supervisor_id).first()
    )
    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    run = Run(
        supervisor_id=data.supervisor_id,
        order_id=data.order_id,
        status="running",
        additional_instructions=data.additional_instructions or "",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Log the order_created event automatically
    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="event",
            payload={
                "event_type": "order_created",
                "order_id": data.order_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()

    # Trigger agent in background immediately
    background_tasks.add_task(run_agent, str(run.id), db, "start")

    return run


@router.get("", response_model=List[RunResponse])
def list_runs(db: Session = Depends(get_db)):
    return db.query(Run).order_by(Run.created_at.desc()).all()


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/activity", response_model=List[ActivityLogResponse])
def get_run_activity(run_id: str, db: Session = Depends(get_db)):
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.run_id == run_id)
        .order_by(ActivityLog.created_at.asc())
        .all()
    )


@router.get("/{run_id}/stats")
def get_run_stats(run_id: str, db: Session = Depends(get_db)):
    """
    Returns operational analytics for a run:
    - Total agent cycles
    - Actions broken down by type
    - Wake trigger breakdown (scheduled vs urgent event vs crash recovery)
    - Time distribution: active vs sleeping
    - Estimated token usage
    - Open issues count from latest state summary
    """
    import json as _json
    from collections import Counter

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    all_entries = (
        db.query(ActivityLog)
        .filter(ActivityLog.run_id == run_id)
        .order_by(ActivityLog.created_at.asc())
        .all()
    )

    # ── Cycle count ──────────────────────────────────────────────────────────
    wake_entries = [e for e in all_entries if e.entry_type == "wake_decision"]
    total_cycles = len(wake_entries)

    # ── Wake trigger breakdown ───────────────────────────────────────────────
    trigger_counts = Counter(e.payload.get("trigger", "unknown") for e in wake_entries)

    # ── Action breakdown ─────────────────────────────────────────────────────
    action_entries = [e for e in all_entries if e.entry_type == "agent_action"]
    action_counts = Counter(e.payload.get("action", "unknown") for e in action_entries)

    # ── Event breakdown ──────────────────────────────────────────────────────
    event_entries = [e for e in all_entries if e.entry_type == "event"]
    event_counts = Counter(
        e.payload.get("event_type", "unknown") for e in event_entries
    )

    # ── Total run duration ────────────────────────────────────────────────────
    start_time = run.created_at
    end_time = run.completed_at or datetime.now(timezone.utc)
    if start_time and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    total_minutes = (end_time - start_time).total_seconds() / 60 if start_time else 0

    # ── Sleep vs active time ─────────────────────────────────────────────────
    # Calculate actual sleep from sleep→wake pairs, not scheduled durations
    sleep_starts = [
        e.created_at for e in all_entries if e.entry_type == "sleep_decision"
    ]
    wake_starts = [e.created_at for e in all_entries if e.entry_type == "wake_decision"]

    total_sleep_minutes = 0
    for sleep_at in sleep_starts:
        if not sleep_at:
            continue
        if sleep_at.tzinfo is None:
            sleep_at = sleep_at.replace(tzinfo=timezone.utc)

        # Find the next wake after this sleep
        actual_wake = None
        for w in wake_starts:
            wt = w.replace(tzinfo=timezone.utc) if w and w.tzinfo is None else w
            if wt and wt > sleep_at:
                actual_wake = wt
                break

        # If no wake followed, sleep ended when the run ended
        sleep_end = actual_wake or end_time
        duration = (sleep_end - sleep_at).total_seconds() / 60
        if 0 < duration < 1440:
            total_sleep_minutes += duration

    # Ensure sleep never exceeds total run time
    total_sleep_minutes = min(total_sleep_minutes, total_minutes)
    active_minutes = max(0, total_minutes - total_sleep_minutes)

    # ── Estimated token usage ─────────────────────────────────────────────────
    # Rough heuristic: each cycle costs ~2000 input tokens + ~300 output tokens
    # This is an estimate — actual usage requires token counting or API metadata
    estimated_input_tokens = total_cycles * 2000
    estimated_output_tokens = total_cycles * 300
    estimated_total_tokens = estimated_input_tokens + estimated_output_tokens

    # ── Open issues from latest state summary ─────────────────────────────────
    open_issues_count = 0
    current_risk_level = "unknown"
    if run.state_summary:
        try:
            summary = _json.loads(run.state_summary)
            open_issues_count = len(summary.get("open_issues", []))
            current_risk_level = summary.get("risk_level", "unknown")
        except (_json.JSONDecodeError, TypeError):
            pass

    # ── Instructions added ────────────────────────────────────────────────────
    instruction_count = len([e for e in all_entries if e.entry_type == "instruction"])

    return {
        "run_id": run_id,
        "order_id": run.order_id,
        "status": run.status,
        "total_cycles": total_cycles,
        "total_actions": len(action_entries),
        "total_events_received": len(event_entries),
        "instructions_added": instruction_count,
        "wake_triggers": dict(trigger_counts),
        "actions_by_type": dict(action_counts),
        "events_by_type": dict(event_counts),
        "time": {
            "total_minutes": round(total_minutes, 1),
            "active_minutes": round(active_minutes, 1),
            "sleeping_minutes": round(total_sleep_minutes, 1),
            "sleep_percentage": round(
                (total_sleep_minutes / total_minutes * 100) if total_minutes > 0 else 0,
                1,
            ),
        },
        "tokens": {
            "estimated_input": estimated_input_tokens,
            "estimated_output": estimated_output_tokens,
            "estimated_total": estimated_total_tokens,
            "note": "Estimated at ~2000 input + ~300 output tokens per cycle",
        },
        "current_risk_level": current_risk_level,
        "open_issues_count": open_issues_count,
    }


@router.post("/{run_id}/events")
def inject_event(
    run_id: str,
    event: EventInject,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in ("terminated", "completed"):
        raise HTTPException(status_code=400, detail="Run is already finished")

    # Log the incoming event
    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="event",
            payload={
                "event_type": event.event_type,
                "data": event.payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()

    # Classifier decides: wake now or wait for schedule
    urgent = is_urgent(event.event_type)

    if urgent and run.status == "sleeping":
        run.status = "running"
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        background_tasks.add_task(run_agent, str(run.id), db, "event")
        return {
            "message": f"Event received. Urgent — agent woken immediately.",
            "urgent": True,
        }

    return {
        "message": f"Event received. Non-urgent — agent will check at next scheduled wake-up.",
        "urgent": False,
    }


@router.post("/{run_id}/instructions")
def add_instructions(run_id: str, data: InstructionAdd, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Append to existing instructions
    existing = run.additional_instructions or ""
    run.additional_instructions = (
        existing
        + f"\n[{datetime.now(timezone.utc).strftime('%H:%M')}] {data.instruction}"
    )
    run.updated_at = datetime.now(timezone.utc)

    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="instruction",
            payload={
                "instruction": data.instruction,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()
    return {"message": "Instruction added to run context"}


@router.post("/{run_id}/interrupt")
def interrupt_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in ("terminated", "completed"):
        raise HTTPException(status_code=400, detail="Run already finished")

    run.status = "interrupted"
    run.updated_at = datetime.now(timezone.utc)
    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="instruction",
            payload={
                "action": "interrupted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()
    return {"message": "Run interrupted"}


@router.post("/{run_id}/resume")
def resume_run(
    run_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "interrupted":
        raise HTTPException(status_code=400, detail="Run is not interrupted")

    run.status = "running"
    run.updated_at = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(run_agent, str(run.id), db, "manual")
    return {"message": "Run resumed"}


@router.post("/{run_id}/terminate")
def terminate_run(
    run_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in ("terminated", "completed"):
        raise HTTPException(status_code=400, detail="Run already finished")

    run.status = "terminated"
    run.completed_at = datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)

    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="instruction",
            payload={
                "action": "terminated_by_user",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()

    # Use a fresh DB session for the background task
    from app.database import SessionLocal

    def run_summary():
        fresh_db = SessionLocal()
        try:
            generate_final_summary(run_id, fresh_db)
        finally:
            fresh_db.close()

    background_tasks.add_task(run_summary)
    return {"message": "Run terminated"}


def generate_final_summary(run_id: str, db: Session):
    """Trigger a final agent run to produce summary and learnings."""
    import json
    from datetime import datetime, timezone

    from app.services.agent import TOOLS, build_context, client, execute_tool

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run or run.final_output:
        return

    supervisor = db.query(Supervisor).filter(Supervisor.id == run.supervisor_id).first()
    if not supervisor:
        return

    context = build_context(run, supervisor, db)

    final_prompt = f"""
{context}

The run has been terminated by the user. Your job now is ONLY to produce a final summary.
You MUST call the complete_run tool with:
- A final_summary of what happened with this order
- The key_actions taken during this run
- Learnings and recommendations for future orders
- Reason: "Terminated by user"

Do not call any other tools. Call complete_run now.
"""

    try:
        response = client.messages.create(
            model=supervisor.model,
            max_tokens=1024,
            system=supervisor.base_instruction,
            messages=[{"role": "user", "content": final_prompt}],
            tools=TOOLS,
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "complete_run":
                # Manually write final output — don't use execute_tool
                # because that would try to set status again
                run.final_output = {
                    "reason": block.input.get("reason", "Terminated by user"),
                    "final_summary": block.input.get("final_summary", ""),
                    "key_actions": block.input.get("key_actions", ""),
                    "learnings": block.input.get("learnings", ""),
                }
                run.updated_at = datetime.now(timezone.utc)

                db.add(
                    ActivityLog(
                        run_id=run.id,
                        entry_type="final_output",
                        payload={
                            **run.final_output,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                )
                db.commit()
                print(f"[Agent] Final summary generated for run {run_id}")
                break

    except Exception as e:
        print(f"[Agent] Final summary failed: {e}")
