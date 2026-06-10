import json
import os
from datetime import datetime, timedelta, timezone

import anthropic
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.models import ActivityLog, Run, Supervisor

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ─────────────────────────────────────────────
# Tool definitions — what the agent can call
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "message_fulfillment_team",
        "description": "Send a message to the fulfillment team about this order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send"}
            },
            "required": ["message"],
        },
    },
    {
        "name": "message_payments_team",
        "description": "Send a message to the payments team about this order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send"}
            },
            "required": ["message"],
        },
    },
    {
        "name": "message_logistics_team",
        "description": "Send a message to the logistics team about this order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send"}
            },
            "required": ["message"],
        },
    },
    {
        "name": "message_customer",
        "description": "Send a message to the customer about their order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send"}
            },
            "required": ["message"],
        },
    },
    {
        "name": "create_internal_note",
        "description": "Create an internal note about this order for future reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "The internal note content"}
            },
            "required": ["note"],
        },
    },
    {
        "name": "sleep_until",
        "description": "Go to sleep and wake up after specified minutes. Use this when no immediate action is needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Minutes to sleep before waking up to check again",
                },
                "reason": {
                    "type": "string",
                    "description": "Why you are sleeping (for the activity log)",
                },
            },
            "required": ["minutes", "reason"],
        },
    },
    {
        "name": "update_state_summary",
        "description": (
            "Update your structured understanding of this order's current state. "
            "Call this on every invocation BEFORE calling sleep_until or complete_run. "
            "All fields are required. Be specific and concise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "current_order_status": {
                    "type": "string",
                    "description": (
                        "The current lifecycle status of the order as you understand it. "
                        "E.g. 'payment_confirmed, awaiting_shipment', 'shipped, in_transit', "
                        "'delivered', 'payment_failed, awaiting_retry'"
                    ),
                },
                "last_action_taken": {
                    "type": "string",
                    "description": (
                        "The most recent action you took this cycle. "
                        "If no action was taken, say 'None — monitored only'."
                    ),
                },
                "open_issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of unresolved issues or concerns you are tracking. "
                        "Empty array if none. E.g. ['payment failure unresolved', "
                        "'customer not yet notified of delay']"
                    ),
                },
                "next_expected_event": {
                    "type": "string",
                    "description": (
                        "What event or development you are waiting for next. "
                        "E.g. 'payment retry confirmation', 'shipment scan update', "
                        "'customer response to message'"
                    ),
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": (
                        "Your assessment of the current risk to order completion. "
                        "low = progressing normally, medium = minor issues being monitored, "
                        "high = active problem requiring escalation."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Any additional context, reasoning, or observations not captured "
                        "in the fields above. Can be empty string."
                    ),
                },
            },
            "required": [
                "current_order_status",
                "last_action_taken",
                "open_issues",
                "next_expected_event",
                "risk_level",
                "notes",
            ],
        },
    },
    {
        "name": "complete_run",
        "description": "Signal that the order has reached a terminal state and the run should end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the run is complete"},
                "final_summary": {
                    "type": "string",
                    "description": "Summary of the entire order lifecycle",
                },
                "key_actions": {
                    "type": "string",
                    "description": "Most important actions taken during this run",
                },
                "learnings": {
                    "type": "string",
                    "description": "Key learnings and recommendations",
                },
            },
            "required": ["reason", "final_summary", "key_actions", "learnings"],
        },
    },
]


# ─────────────────────────────────────────────
# Tool execution — what happens when agent calls a tool
# ─────────────────────────────────────────────


def execute_tool(tool_name: str, tool_input: dict, run: Run, db: Session) -> str:
    """Execute a tool call and log it to activity_log. Returns result string."""

    if tool_name in [
        "message_fulfillment_team",
        "message_payments_team",
        "message_logistics_team",
        "message_customer",
    ]:
        message_key = "message"
        team = tool_name.replace("message_", "").replace("_", " ").title()
        log_entry = ActivityLog(
            run_id=run.id,
            entry_type="agent_action",
            payload={
                "action": tool_name,
                "team": team,
                "message": tool_input.get(message_key, ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(log_entry)
        db.commit()
        return f"Message sent to {team}"

    elif tool_name == "create_internal_note":
        log_entry = ActivityLog(
            run_id=run.id,
            entry_type="agent_action",
            payload={
                "action": "create_internal_note",
                "note": tool_input.get("note", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(log_entry)
        db.commit()
        return "Internal note created"

    elif tool_name == "sleep_until":
        minutes = tool_input.get("minutes", 30)
        reason = tool_input.get("reason", "")
        wake_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

        run.status = "sleeping"
        run.wake_at = wake_at
        run.updated_at = datetime.now(timezone.utc)

        log_entry = ActivityLog(
            run_id=run.id,
            entry_type="sleep_decision",
            payload={
                "reason": reason,
                "wake_at": wake_at.isoformat(),
                "minutes": minutes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(log_entry)
        db.commit()
        return f"Sleeping for {minutes} minutes, will wake at {wake_at.isoformat()}"

    elif tool_name == "update_state_summary":
        import json as _json

        # Validate required fields are present
        required_fields = [
            "current_order_status",
            "last_action_taken",
            "open_issues",
            "next_expected_event",
            "risk_level",
            "notes",
        ]
        missing = [f for f in required_fields if f not in tool_input]
        if missing:
            # Log the validation failure — don't silently accept a bad summary
            db.add(
                ActivityLog(
                    run_id=run.id,
                    entry_type="reasoning",
                    payload={
                        "warning": "update_state_summary called with missing fields",
                        "missing_fields": missing,
                        "received": tool_input,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            db.commit()
            return f"Validation failed: missing fields {missing}. Summary not saved."

        # Validate risk_level is a known value
        if tool_input.get("risk_level") not in ("low", "medium", "high"):
            return "Validation failed: risk_level must be 'low', 'medium', or 'high'."

        # Store as structured JSON string on the run
        structured_summary = {
            "current_order_status": tool_input["current_order_status"],
            "last_action_taken": tool_input["last_action_taken"],
            "open_issues": tool_input["open_issues"],
            "next_expected_event": tool_input["next_expected_event"],
            "risk_level": tool_input["risk_level"],
            "notes": tool_input["notes"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        run.state_summary = _json.dumps(structured_summary)
        run.updated_at = datetime.now(timezone.utc)
        db.add(run)

        # Build a human-readable summary for the frontend
        issues_text = (
            ", ".join(tool_input["open_issues"])
            if tool_input["open_issues"]
            else "none"
        )
        readable_summary = (
            f"Status: {tool_input['current_order_status']}. "
            f"Last action: {tool_input['last_action_taken']}. "
            f"Issues: {issues_text}. "
            f"Next: {tool_input['next_expected_event']}. "
            f"Risk: {tool_input['risk_level']}."
            + (f" Notes: {tool_input['notes']}" if tool_input["notes"] else "")
        )

        db.add(
            ActivityLog(
                run_id=run.id,
                entry_type="reasoning",
                payload={
                    **structured_summary,
                    "summary": readable_summary,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        db.commit()
        return "Structured state summary saved."

    elif tool_name == "complete_run":
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        run.final_output = {
            "reason": tool_input.get("reason", ""),
            "final_summary": tool_input.get("final_summary", ""),
            "key_actions": tool_input.get("key_actions", ""),
            "learnings": tool_input.get("learnings", ""),
        }

        log_entry = ActivityLog(
            run_id=run.id,
            entry_type="final_output",
            payload={
                **run.final_output,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(log_entry)
        db.commit()
        return "Run completed"

    return "Unknown tool"


# ─────────────────────────────────────────────
# Build context for the agent
# ─────────────────────────────────────────────


def build_context(run: Run, supervisor: Supervisor, db: Session) -> str:
    """Build the full context string to pass to the agent."""

    # Get last 20 activity log entries for context
    recent_activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.run_id == run.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )

    recent_activity.reverse()  # chronological order

    activity_text = ""
    for entry in recent_activity:
        ts = entry.created_at.strftime("%H:%M:%S") if entry.created_at else "unknown"
        activity_text += (
            f"[{ts}] {entry.entry_type.upper()}: {json.dumps(entry.payload)}\n"
        )

    import json as _json

    try:
        summary_data = _json.loads(run.state_summary) if run.state_summary else None
        if summary_data and isinstance(summary_data, dict):
            summary_text = (
                f"Order status   : {summary_data.get('current_order_status', 'unknown')}\n"
                f"Last action    : {summary_data.get('last_action_taken', 'none')}\n"
                f"Open issues    : {', '.join(summary_data.get('open_issues', [])) or 'none'}\n"
                f"Next expected  : {summary_data.get('next_expected_event', 'unknown')}\n"
                f"Risk level     : {summary_data.get('risk_level', 'unknown')}\n"
                f"Notes          : {summary_data.get('notes', '')}"
            )
        else:
            summary_text = (
                run.state_summary or "No summary yet — this may be the first run."
            )
    except (_json.JSONDecodeError, TypeError):
        summary_text = (
            run.state_summary or "No summary yet — this may be the first run."
        )

    context = f"""
ORDER ID: {run.order_id}
RUN STARTED: {run.created_at}
CURRENT TIME: {datetime.now(timezone.utc).isoformat()}
CURRENT STATUS: {run.status}

YOUR CURRENT STATE SUMMARY:
{summary_text}

ADDITIONAL INSTRUCTIONS FOR THIS RUN:
{run.additional_instructions or "None"}

RECENT ACTIVITY LOG (last 20 entries):
{activity_text or "No activity yet."}

Based on the above context, decide what to do next.
- If action is needed, call the appropriate tool(s).
- Always call update_state_summary to record your current understanding.
- When done acting, call sleep_until with appropriate minutes.
- If the order has reached a terminal state (delivered, refund_completed, etc.), call complete_run.
- Be concise. Explain your reasoning briefly before acting.
"""
    return context


# ─────────────────────────────────────────────
# Main agent runner
# ─────────────────────────────────────────────


def run_agent(run_id: str, db: Session, trigger: str = "scheduled"):
    """
    Main entry point. Wakes the agent, runs it, handles tool calls.
    trigger: 'start' | 'event' | 'scheduled' | 'manual'
    """

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        print(f"[Agent] Run {run_id} not found")
        return

    # Don't run if terminated or completed
    if run.status in ("terminated", "completed"):
        print(f"[Agent] Run {run_id} is {run.status}, skipping")
        return

    supervisor = db.query(Supervisor).filter(Supervisor.id == run.supervisor_id).first()
    if not supervisor:
        print(f"[Agent] Supervisor not found for run {run_id}")
        return

    # Mark as running
    run.status = "running"
    run.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Log wake event
    db.add(
        ActivityLog(
            run_id=run.id,
            entry_type="wake_decision",
            payload={
                "trigger": trigger,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    db.commit()

    print(f"[Agent] Running agent for run {run_id}, trigger={trigger}")

    # Build context
    context = build_context(run, supervisor, db)

    # Call Claude with tools
    try:
        response = client.messages.create(
            model=supervisor.model,
            max_tokens=1024,
            system=supervisor.base_instruction,
            messages=[{"role": "user", "content": context}],
            tools=TOOLS,
        )
    except Exception as e:
        print(f"[Agent] LLM call failed: {e}")
        # Put back to sleeping so scheduler retries
        run.status = "sleeping"
        run.wake_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.commit()
        return

    # Process response blocks - log text reasoning, execute tool calls
    tool_was_called = False
    for block in response.content:
        if block.type == "text" and block.text.strip():
            db.add(
                ActivityLog(
                    run_id=run.id,
                    entry_type="reasoning",
                    payload={
                        "summary": block.text.strip(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            db.commit()
        if block.type == "tool_use":
            tool_was_called = True
            print(f"[Agent] Tool called: {block.name} with {block.input}")
            result = execute_tool(block.name, block.input, run, db)
            print(f"[Agent] Tool result: {result}")

            # If agent called sleep or complete, stop processing
            if block.name in ("sleep_until", "complete_run"):
                break

    # If agent didn't call sleep or complete, default to sleeping
    if not tool_was_called or run.status == "running":
        run.status = "sleeping"
        run.wake_at = datetime.now(timezone.utc) + timedelta(
            minutes=supervisor.default_wake_interval_minutes
        )
        run.updated_at = datetime.now(timezone.utc)
        db.add(
            ActivityLog(
                run_id=run.id,
                entry_type="sleep_decision",
                payload={
                    "reason": "Agent finished without explicit sleep call — defaulting to scheduled wake",
                    "wake_at": run.wake_at.isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        db.commit()

    print(f"[Agent] Run {run_id} done. Status now: {run.status}")
