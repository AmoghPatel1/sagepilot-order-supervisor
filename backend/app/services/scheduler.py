import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import ActivityLog, Run

scheduler = BackgroundScheduler()

# ─────────────────────────────────────────────
# Job 1: Wake sleeping runs whose wake_at has passed
# ─────────────────────────────────────────────


def check_sleeping_runs():
    """Poll for sleeping runs whose wake_at has passed. Trigger agent for each."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due_runs = (
            db.query(Run).filter(Run.status == "sleeping", Run.wake_at <= now).all()
        )

        if due_runs:
            print(f"[Scheduler] Found {len(due_runs)} runs to wake up")

        for run in due_runs:
            print(f"[Scheduler] Waking run {run.id}")
            from app.services.agent import run_agent

            run_agent(str(run.id), db, trigger="scheduled")

    except Exception as e:
        print(f"[Scheduler] check_sleeping_runs error: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# Job 2: Auto-terminate runs older than MAX_RUN_AGE_HOURS
# ─────────────────────────────────────────────


def terminate_stale_runs():
    """Auto-terminate runs older than MAX_RUN_AGE_HOURS."""
    MAX_HOURS = int(os.getenv("MAX_RUN_AGE_HOURS", "24"))
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS)
        stale = (
            db.query(Run)
            .filter(
                Run.status.not_in(["completed", "terminated"]), Run.created_at <= cutoff
            )
            .all()
        )

        for run in stale:
            print(f"[Scheduler] Auto-terminating stale run {run.id}")
            run.status = "terminated"
            run.completed_at = datetime.now(timezone.utc)
            run.updated_at = datetime.now(timezone.utc)
            db.add(
                ActivityLog(
                    run_id=run.id,
                    entry_type="final_output",
                    payload={
                        "action": "auto_terminated_max_age",
                        "reason": f"Run exceeded max age of {MAX_HOURS} hours",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
        if stale:
            db.commit()
            print(f"[Scheduler] Auto-terminated {len(stale)} stale runs")

    except Exception as e:
        print(f"[Scheduler] terminate_stale_runs error: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# Job 3 (NEW): Crash recovery — reset stuck 'running' runs
# ─────────────────────────────────────────────


def recover_stuck_runs():
    """
    Detect runs stuck in 'running' status — a symptom of a server crash
    mid-agent-invocation. Resets them to 'sleeping' so the scheduler
    picks them up on the next cycle.

    A run is considered stuck if it has been in 'running' status for longer
    than STUCK_RUN_TIMEOUT_MINUTES. Normal agent invocations complete in
    seconds; anything beyond a few minutes is almost certainly a crash artifact.
    """
    TIMEOUT_MINUTES = int(os.getenv("STUCK_RUN_TIMEOUT_MINUTES", "10"))
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=TIMEOUT_MINUTES)
        stuck_runs = (
            db.query(Run)
            .filter(Run.status == "running", Run.updated_at <= cutoff)
            .all()
        )

        for run in stuck_runs:
            print(
                f"[Scheduler] Recovering stuck run {run.id} "
                f"(stuck since {run.updated_at})"
            )

            # Reset to sleeping with a short wake interval
            # so the agent retries promptly
            run.status = "sleeping"
            run.wake_at = datetime.now(timezone.utc) + timedelta(minutes=1)
            run.updated_at = datetime.now(timezone.utc)

            # Log the recovery so it's visible in the activity timeline
            db.add(
                ActivityLog(
                    run_id=run.id,
                    entry_type="wake_decision",
                    payload={
                        "trigger": "crash_recovery",
                        "reason": (
                            f"Run was stuck in 'running' status for >{TIMEOUT_MINUTES} minutes. "
                            "Likely caused by a server crash mid-invocation. "
                            "Reset to sleeping — agent will retry on next scheduler cycle."
                        ),
                        "stuck_since": run.updated_at.isoformat()
                        if run.updated_at
                        else None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )

        if stuck_runs:
            db.commit()
            print(f"[Scheduler] Recovered {len(stuck_runs)} stuck runs")

    except Exception as e:
        print(f"[Scheduler] recover_stuck_runs error: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# Scheduler startup / shutdown
# ─────────────────────────────────────────────


def start_scheduler():
    # Core wake job — every 30 seconds
    scheduler.add_job(check_sleeping_runs, "interval", seconds=30, id="wake_sleeping")

    # Stale run cleanup — every 10 minutes
    scheduler.add_job(
        terminate_stale_runs, "interval", minutes=10, id="terminate_stale"
    )

    # Crash recovery — every 5 minutes
    # Runs slightly more frequently than the timeout so recovery is prompt
    scheduler.add_job(recover_stuck_runs, "interval", minutes=5, id="crash_recovery")

    scheduler.start()
    print("[Scheduler] Started:")
    print("  - Wake sleeping runs: every 30s")
    print("  - Terminate stale runs: every 10m")
    print("  - Crash recovery: every 5m")


def stop_scheduler():
    scheduler.shutdown()
