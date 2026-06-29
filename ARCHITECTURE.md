# Architecture & Design Note

## Overview

AI Order Supervisor is a long-running AI agent system that monitors e-commerce
orders from creation to completion. The core design challenge is not the AI itself —
it is modeling a process that persists across hours, receives external events
asynchronously, and resumes coherently after sleeping. This document explains every
major design decision and the tradeoffs that led to it.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                         │
│  Supervisors │ Runs List │ Run Detail (Activity / State / Summary) │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP (REST)
┌─────────────────────▼───────────────────────────────────────────┐
│                      FastAPI Backend                            │
│                                                                 │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │   API Routers   │    │         APScheduler              │   │
│  │  /supervisors   │    │  polls every 30s                 │   │
│  │  /runs          │    │  finds sleeping runs where       │   │
│  │  /runs/events   │    │  wake_at <= now                  │   │
│  │  /runs/instruct │    │  → triggers agent                │   │
│  └────────┬────────┘    └──────────────┬───────────────────┘   │
│           │                            │                        │
│  ┌────────▼────────────────────────────▼───────────────────┐   │
│  │                   Agent Service                          │   │
│  │                                                          │   │
│  │  build_context()  →  Claude API (tool use)  →           │   │
│  │  execute_tool()   →  activity_log insert                 │   │
│  │                                                          │   │
│  │  Tools: message_fulfillment_team                         │   │
│  │         message_payments_team                            │   │
│  │         message_logistics_team                           │   │
│  │         message_customer                                 │   │
│  │         create_internal_note                             │   │
│  │         sleep_until                                      │   │
│  │         update_state_summary                             │   │
│  │         complete_run                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Classifier Service                          │   │
│  │  is_urgent(event_type) → bool                            │   │
│  │  Urgent → wake agent now                                 │   │
│  │  Non-urgent → wait for next scheduled wake               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                    PostgreSQL (Supabase)                         │
│                                                                 │
│  supervisors    runs              activity_log                  │
│  ─────────────  ────────────────  ─────────────────────────     │
│  id             id                id                           │
│  name           supervisor_id     run_id                       │
│  base_instr     order_id          entry_type                   │
│  actions[]      status            payload (JSONB)              │
│  wake_interval  wake_at           created_at                   │
│  model          state_summary                                  │
│                 additional_instr                               │
│                 final_output                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Orchestration Choice: DB State + APScheduler

### What was considered

| Option | Pros | Cons |
|---|---|---|
| **DB + APScheduler** | Zero extra infrastructure, fully restartable, simple to debug | No durable execution guarantee, scheduler in same process |
| **Temporal** | Durable execution, built-in sleep/wake, battle-tested | Requires Temporal server + worker setup, steep learning curve, 1-2 day setup cost |
| **Redis + Celery** | High throughput, battle-tested queue | Adds Redis infrastructure, designed for short tasks not long-running state |
| **Simple cron** | Simplest possible | No event-driven wake, pure polling only |

### Why DB + APScheduler

Temporal is the "correct" production answer for durable long-running workflows.
However, it requires running a Temporal server (Go binary or Docker), configuring
namespaces, and writing workflow code in their SDK. For this scope, that setup
cost would consume Day 1 entirely — time better spent on the agent logic itself.

The key insight is that DB state + a scheduler achieves the **same logical model**
as Temporal's sleep/wake primitives:

- `sleep_until(minutes=30)` in Temporal = set `wake_at = now + 30m, status = sleeping` in PostgreSQL
- Temporal's durable timer = APScheduler polling for `wake_at <= now`
- Temporal's signal = our `POST /events` endpoint that wakes a sleeping run

The difference is failure handling. If the server crashes mid-agent-invocation
in our system, the run stays in `running` status. Temporal would replay the
workflow from the last checkpoint. For a single-machine deployment, this tradeoff is explicit
and acceptable — all state is in the database and survives restarts, only the
in-flight LLM call is lost.

### How sleep/wake works

```
Agent invocation
      │
      ▼
Claude API call with context
      │
      ▼
Tool calls in response
      ├── Business action → activity_log insert
      ├── update_state_summary → runs.state_summary update
      └── sleep_until(minutes=N)
              │
              ▼
         runs.status = 'sleeping'
         runs.wake_at = now + N minutes
              │
              ▼ (30 seconds later, APScheduler polls)
         SELECT * FROM runs
         WHERE status = 'sleeping'
         AND wake_at <= now
              │
              ▼
         Agent invocation (trigger='scheduled')
```

---

## Agent Design: Direct Anthropic SDK + Tool Use

### Why not LangChain

LangChain abstracts tool calling, memory, and chains. In this system:

- **Tool calling** is handled by the Anthropic SDK directly — Claude returns
  `tool_use` blocks, we execute them, that's it
- **Memory** is the `state_summary` field, updated explicitly by the agent
  calling `update_state_summary`
- **"Chains"** are just sequential tool calls within a single LLM response

LangChain would add a layer of abstraction over all three without simplifying
any of them. Direct SDK usage means every step is a Python function call that
can be logged, tested, and debugged without framework magic.

### Tool design

The agent has 8 tools split into two categories:

**Business action tools** — each writes an `activity_log` record, nothing more.
No external calls are made. The log record is the action.

```python
message_fulfillment_team(message: str)
message_payments_team(message: str)
message_logistics_team(message: str)
message_customer(message: str)
create_internal_note(note: str)
```

**Runtime tools** — control the agent's own lifecycle:

```python
sleep_until(minutes: int, reason: str)
# Sets wake_at, flips status to sleeping, logs sleep decision

update_state_summary(summary: str)
# Compresses current understanding into runs.state_summary

complete_run(reason, final_summary, key_actions, learnings)
# Writes final_output JSON, marks run completed
```

### Why the agent cannot end its own run

System-owned completion rules are required. `complete_run` signals
intent but completion also triggers on:
- Manual termination from the UI
- A configured max run age (extensible)

This separation matters: an agent that hallucinates a terminal state should not
silently end a run. The system layer validates lifecycle transitions.

### Context building

Each agent invocation receives:

```
ORDER ID: {order_id}
RUN STARTED: {created_at}
CURRENT TIME: {now}
CURRENT STATUS: {status}

YOUR CURRENT STATE SUMMARY:
{state_summary}            ← compressed memory from last cycle

ADDITIONAL INSTRUCTIONS FOR THIS RUN:
{additional_instructions}  ← injected mid-run by user

RECENT ACTIVITY LOG (last 20 entries):
{activity_log[-20:]}       ← sliding window of recent events
```

The agent never receives the full activity log — only the last 20 entries plus
the compressed summary. This keeps token usage bounded regardless of run duration.

---

## Event Wake/Sleep Model

### Two-tier event handling

```
Incoming event (POST /runs/{id}/events)
         │
         ▼
  Classifier.is_urgent(event_type)
         │
    ┌────┴────┐
  urgent    not urgent
    │            │
    ▼            ▼
Wake agent   Log event,
immediately  wait for next
             scheduled wake
```

The classifier is a pure Python function — no LLM call, no network, instant:

```python
URGENT_EVENTS = {
    "payment_failed",
    "refund_requested",
    "customer_message_received",
    "shipment_delayed",
    "delivered",
}

NON_URGENT_EVENTS = {
    "order_created",
    "payment_confirmed",
    "shipment_created",
    "no_update_for_n_hours",
}

def is_urgent(event_type: str) -> bool:
    if event_type in URGENT_EVENTS:
        return True
    if event_type in NON_URGENT_EVENTS:
        return False
    return True  # unknown events default to urgent
```

### Urgency logic rationale

**Urgent**: events that require immediate intervention — a payment failure needs
the payments team and customer notified now, not in 30 minutes. A delivery event
should trigger run completion immediately.

**Non-urgent**: events that confirm expected progression — payment confirmation
after an order is good news but requires no action. The agent will see it on
the next scheduled wake.

**Unknown events default to urgent** because the cost of missing a critical event
outweighs the cost of an unnecessary LLM call.

---

## State and Memory Design

### The problem

An LLM has no memory between calls. A run can span hours and accumulate hundreds
of activity log entries. Passing the full history to every invocation is:
- Expensive (tokens scale linearly with history length)
- Eventually impossible (context window limit)

### The solution: compressed prefix + sliding window

```
Invocation N:
┌────────────────────────────────────────────┐
│ state_summary (compressed, ~200 tokens)    │  ← written by agent at invocation N-1
│ activity_log[-20] (~400 tokens)            │  ← last 20 entries
└────────────────────────────────────────────┘

Invocation N+1:
┌────────────────────────────────────────────┐
│ state_summary (updated by invocation N)    │  ← agent updates this every cycle
│ activity_log[-20] (~400 tokens)            │  ← sliding window advances
└────────────────────────────────────────────┘
```

The agent is prompted to call `update_state_summary` on every invocation. This
means the state_summary always reflects the latest understanding, and older
activity entries can fall off the sliding window without losing information.

### Tradeoff

This approach is simple and cheap. The weakness is that if something important
happened 25 events ago and the agent failed to include it in the summary, it is
effectively forgotten. A production system would use a more sophisticated
compaction strategy — tiered summarization, semantic retrieval, or explicit
"memory" fields per event category.

---

## Database Schema Design

A single `activity_log` table handles all temporal data:

```sql
activity_log.entry_type:
  'event'          -- incoming order events
  'wake_decision'  -- agent was triggered (with trigger reason)
  'agent_action'   -- business action executed by agent
  'sleep_decision' -- agent decided to sleep (with wake_at)
  'reasoning'      -- state summary updates
  'instruction'    -- manual instructions added mid-run
  'final_output'   -- end-of-run summary
```

This single-table design was a deliberate choice over separate tables for events,
actions, and messages. The tradeoff: querying specific entry types requires
filtering on `entry_type`, but the gain is a single chronological timeline that
is easy to display and reason about. The UI renders the full timeline in order —
a split-table design would require joining and sorting across multiple tables to
achieve the same view.

The `payload` column is JSONB, allowing each entry type to carry its own structure
without schema migrations as the system evolves.

---

## Run Lifecycle State Machine

```
         ┌──────────┐
         │  created │
         └────┬─────┘
              │ POST /runs triggers agent
              ▼
         ┌──────────┐
    ┌───►│ running  │◄──────────────────────┐
    │    └────┬─────┘                       │
    │         │ agent calls sleep_until      │ resume / urgent event
    │         ▼                             │
    │    ┌──────────┐    interrupt     ┌────┴───────┐
    │    │ sleeping │─────────────────►│ interrupted│
    │    └────┬─────┘                  └────────────┘
    │         │ wake_at reached
    └─────────┘ (APScheduler)

    Any state ──► terminate ──► terminated
    Agent calls complete_run ──► completed
```

**Terminal states**: `completed`, `terminated`
- No further agent invocations
- Final summary generated on entry to terminal state

---

## API Design

The API follows REST conventions with resource-oriented endpoints.
Run control actions use POST rather than PUT/PATCH because they are
commands that trigger side effects (agent invocations, background tasks),
not idempotent state updates.

```
POST /api/runs/{id}/events       → classifier → optional agent wake
POST /api/runs/{id}/instructions → appends to run context
POST /api/runs/{id}/interrupt    → sets status=interrupted
POST /api/runs/{id}/resume       → sets status=running, triggers agent
POST /api/runs/{id}/terminate    → sets status=terminated, generates summary
```

---

## Known Limitations and Production Path

| Limitation | Impact | Production Fix |
|---|---|---|
| No crash recovery for in-flight runs | Run stuck in `running` if server crashes mid-invocation | Startup job that resets `running` runs older than N minutes to `sleeping` |
| Scheduler in same process as API | Agent invocations could slow API responses under load | Separate worker process; APScheduler in dedicated service |
| 30-second scheduler polling | Wake-ups up to 30 seconds late | Reduce poll interval, or use pg_notify for instant wake |
| Naive context compaction | Events older than 20 entries may be lost if not summarized | Tiered summarization, per-category memory fields |
| No authentication | Single-tenant only | Add JWT auth layer; add user_id FK to runs and supervisors |
| No idempotency on event injection | Duplicate events possible if client retries | Add event_id deduplication on activity_log |
