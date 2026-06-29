# AI Order Supervisor

AI Order Supervisor is a long-running AI agent that monitors e-commerce orders from creation to completion. The core challenge: building an AI system that persists coherently across hours of operation — waking on urgent events, maintaining structured memory between sleep cycles, reasoning about order health, and executing business actions — without a persistent process or heavyweight orchestration framework.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Stack](#stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Database Setup](#database-setup)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the App](#running-the-app)
- [Using the App](#using-the-app)
- [Event Types](#event-types)
- [API Reference](#api-reference)
- [Key Design Decisions](#key-design-decisions)
- [Known Limitations](#known-limitations)

---

## What It Does

When an order is created, the system starts a long-running **run** for that order. An AI agent (Claude) supervises the run:

- **Wakes immediately** when urgent events arrive (payment failure, shipment delay, customer message)
- **Stays asleep** for non-urgent events (payment confirmed, shipment created) until the next scheduled check
- **Executes business actions**: messaging the fulfillment team, payments team, logistics team, or customer, and creating internal notes
- **Maintains structured state** across wake cycles via a validated JSON state summary with required fields
- **Recovers automatically** from server crashes — runs stuck in `running` status are reset to `sleeping` by a background recovery job
- **Produces a final summary** with key actions, learnings, and recommendations when the run ends
- **Surfaces run analytics** — cycle counts, wake trigger breakdown, action breakdown, time distribution, and estimated token usage

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), Tailwind CSS v4 |
| Backend | Python 3.11, FastAPI, APScheduler |
| Database | PostgreSQL via Supabase |
| LLM | Anthropic Claude (claude-haiku-4-5) — direct SDK, tool use |

---

## Project Structure

```
ai-order-supervisor/
├── schema.sql                  # Run this in Supabase to create all tables
├── README.md
├── ARCHITECTURE.md
├── DESIGN_NOTE.md
│
├── backend/
│   ├── .env                    # Your secrets (not committed)
│   └── app/
│       ├── main.py             # FastAPI app entry point, CORS, scheduler startup
│       ├── database.py         # SQLAlchemy engine and session factory
│       ├── models.py           # ORM models: Supervisor, Run, ActivityLog
│       ├── schemas.py          # Pydantic request/response schemas
│       ├── routers/
│       │   ├── supervisors.py  # CRUD for supervisor configs
│       │   └── runs.py         # Run lifecycle, events, instructions, controls, stats
│       └── services/
│           ├── agent.py        # LLM agent: tools, tool execution, context builder
│           ├── classifier.py   # Event urgency classifier (no LLM, pure Python)
│           └── scheduler.py    # APScheduler: wake, stale termination, crash recovery
│
└── frontend/
    ├── .env.local              # API URL (not committed)
    └── app/
        ├── page.tsx            # Home page
        ├── globals.css         # Tailwind v4 import
        ├── lib/
        │   └── api.ts          # Axios client + shared TypeScript types
        ├── supervisors/
        │   └── page.tsx        # Supervisor list + create form
        └── runs/
            ├── page.tsx        # Runs list (active + completed, auto-refreshes)
            ├── new/
            │   └── page.tsx    # New run form
            └── [id]/
                └── page.tsx    # Run detail: activity log, state, summary, stats, controls
```

---

## Prerequisites

- **Node.js** v18 or higher
- **Python** 3.11
- A **Supabase** account (free tier works)
- An **Anthropic API key** with credits added

---

## Database Setup

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Wait for the project to finish provisioning (~2 minutes)
3. Go to **SQL Editor** in the left sidebar
4. Copy the contents of `schema.sql` from this repo and run it

This creates three tables (`supervisors`, `runs`, `activity_log`) and inserts a default supervisor template.

### Getting your connection string

Go to **Project Settings → Database → Connection pooling** and copy the **Connection string**. It looks like:

```
postgresql://postgres.yourref:password@aws-0-region.pooler.supabase.com:6543/postgres
```

> **Important**: Use the **pooler** connection string (port `6543`), not the direct connection (port `5432`). The direct connection times out on Windows due to IPv6/firewall behavior.

---

## Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary apscheduler python-dotenv anthropic
```

### Create `backend/.env`

```env
DATABASE_URL=postgresql://postgres.yourref:yourpassword@aws-0-region.pooler.supabase.com:6543/postgres
ANTHROPIC_API_KEY=sk-ant-your-key-here
MAX_RUN_AGE_HOURS=24
STUCK_RUN_TIMEOUT_MINUTES=10
```

**Rules for the database password:**
- No special characters (`@`, `#`, `$`, `%`) — they break the URL
- If your password has special characters, reset it in Supabase → Project Settings → Database → Reset database password

---

## Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

### Create `frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Running the App

You need two terminals open simultaneously.

**Terminal 1 — Backend:**

```bash
cd backend
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

uvicorn app.main:app --reload --port 8000
```

You should see:
```
[Scheduler] Started:
  - Wake sleeping runs: every 30s
  - Terminate stale runs: every 10m
  - Crash recovery: every 5m
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

**API docs** are available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Using the App

### 1. Configure a Supervisor

Go to **Supervisors** → view the default template or create a new one.

A supervisor defines:
- **Name** — identifier for this template
- **Base Instruction** — the system prompt the agent operates under
- **Wake Interval** — how many minutes to sleep between scheduled checks
- **Aggressiveness** — hint to the agent about how proactively to act
- **Model** — which Claude model to use (Haiku is fast and cheap; Sonnet is smarter)

Hardcoded templates are fine — the default one works out of the box.

### 2. Start a Run

Click **Start a run with this supervisor** → set an Order ID → optionally add initial instructions (e.g. `"Escalate immediately if shipment is delayed"`) → click **Start Run**.

You are redirected to the run detail page. Within a few seconds, the agent wakes up for the first time, writes a structured state summary, and goes back to sleep.

### 3. Inject Events

On the run detail page, use the **Inject Event** panel on the right:

- Select an event type from the dropdown
- Optionally add a JSON payload (e.g. `{"reason": "card declined"}`)
- Click **Send Event**

Urgent events wake the agent immediately. Non-urgent events are queued until the next scheduled wake-up.

### 4. Add Instructions Mid-Run

Type an instruction in the **Add Instruction** panel and click **Add Instruction**. The instruction is appended to the run context and the agent will see it on its next wake-up. Example:

```
Do not contact the customer without escalating to the payments team first.
```

### 5. Monitor the Activity Log

The **Activity** tab shows a live timeline of everything that has happened:

| Entry Type | What it means |
|---|---|
| Event | An incoming order event |
| Woke Up | Agent was triggered (shows trigger reason: scheduled / event / crash_recovery) |
| Action | A business action the agent executed |
| Sleeping | Agent decided to sleep (shows wake time) |
| Reasoning | Agent's structured state summary update |
| Instruction | A manual instruction was added |
| Final Output | End-of-run summary |

The page auto-refreshes every 3 seconds.

### 6. View Structured State

The **State** tab shows the agent's current structured understanding of the order:

- **Order Status** — lifecycle state as the agent understands it
- **Risk Level** — low / medium / high assessment
- **Last Action Taken** — most recent intervention this cycle
- **Open Issues** — unresolved concerns the agent is tracking
- **Next Expected Event** — what the agent is waiting for
- **Agent Notes** — additional context

This updates every time the agent completes a cycle.

### 7. View Run Analytics

The **Stats** tab surfaces operational metrics for the run:

- Total agent cycles, actions, and events received
- Wake trigger breakdown (scheduled vs urgent event vs crash recovery)
- Active vs sleeping time distribution
- Actions broken down by type
- Estimated token usage

### 8. Control the Run

- **Pause** — pauses the run (agent will not wake on schedule or events)
- **Resume** — resumes a paused run and immediately triggers the agent
- **Terminate** — ends the run permanently and generates a final summary

### 9. View the Final Summary

After a run completes or is terminated, click the **Summary** tab to see:

- **Final Summary** — what happened across the order lifecycle
- **Key Actions Taken** — the most important interventions the agent made
- **Learnings** — what worked and what could be improved
- **Completion Reason** — why the run ended

---

## Event Types

| Event | Urgency | Typical Agent Response |
|---|---|---|
| `order_created` | Non-urgent | Acknowledges, sets up monitoring |
| `payment_confirmed` | Non-urgent | Notes confirmation, continues monitoring |
| `payment_failed` | **Urgent** | Messages payments team, customer, and fulfillment team |
| `shipment_created` | Non-urgent | Notes shipment, schedules check-in |
| `shipment_delayed` | **Urgent** | Messages logistics team and customer |
| `delivered` | **Urgent** | Confirms delivery, triggers run completion |
| `refund_requested` | **Urgent** | Messages payments team, creates internal note |
| `customer_message_received` | **Urgent** | Escalates to relevant team |
| `no_update_for_n_hours` | Non-urgent | Checks status on next wake |

Unknown event types default to **urgent** — safer to over-wake than miss something critical.

---

## API Reference

All endpoints are prefixed with `/api`. Full interactive docs at `http://localhost:8000/docs`.

### Supervisors

```
GET    /api/supervisors              List all supervisors
POST   /api/supervisors              Create a supervisor
GET    /api/supervisors/{id}         Get a supervisor
```

### Runs

```
GET    /api/runs                     List all runs
POST   /api/runs                     Create a run (triggers agent immediately)
GET    /api/runs/{run_id}            Get a run
GET    /api/runs/{run_id}/activity   Get full activity log for a run
GET    /api/runs/{run_id}/stats      Get run analytics and operational metrics
POST   /api/runs/{run_id}/events     Inject an event into a run
POST   /api/runs/{run_id}/instructions  Add an instruction to a live run
POST   /api/runs/{run_id}/interrupt  Pause a run
POST   /api/runs/{run_id}/resume     Resume a paused run
POST   /api/runs/{run_id}/terminate  Terminate a run (generates final summary)
```

### Health

```
GET    /health                       Returns {"status": "ok"}
```

---

## Key Design Decisions

**DB state + APScheduler over Temporal**
Temporal offers durable execution but requires significant infrastructure setup. For this scope, database state + a background scheduler achieves the same logical model (sleep = a row with a future timestamp, wake = a poll that finds that row) with zero additional infrastructure. The system is fully restartable — all state lives in PostgreSQL.

**Direct Anthropic SDK over LangChain**
The agent's tool-calling, memory, and reasoning are handled explicitly without a framework. Tool calling uses the Anthropic SDK directly, memory is the structured `state_summary` field updated each cycle, and multi-step reasoning is sequential tool calls in a single LLM response. This makes every step visible and debuggable.

**Structured state summary with validation**
The agent writes a structured JSON summary on every cycle with six required fields: `current_order_status`, `last_action_taken`, `open_issues`, `next_expected_event`, `risk_level`, and `notes`. Missing fields are rejected and logged — the agent cannot silently write an incomplete summary. This replaces free-text memory with a validated, queryable schema.

**Crash recovery via background job**
A scheduler job runs every 5 minutes and resets runs stuck in `running` status for longer than `STUCK_RUN_TIMEOUT_MINUTES` back to `sleeping`. Stuck runs are a symptom of a server crash mid-invocation. Recovery is logged to the activity timeline with `trigger: crash_recovery` so it is visible and auditable.

**Lightweight classifier for event urgency**
Every incoming event passes through a pure Python classifier before the agent is invoked. Urgent events wake the agent immediately; non-urgent events wait for the scheduled wake-up. This avoids an LLM call for every event, keeping costs low while ensuring critical events get immediate attention.

**Sliding window context with compressed prefix**
The agent receives its structured `state_summary` plus the last 20 activity log entries on each wake-up. This bounds token usage regardless of how long the run has been active.

See `ARCHITECTURE.md` for the system architecture and `DESIGN_NOTE.md` for 
the reasoning and tradeoffs behind each design decision.

---

## Known Limitations

- **Scheduler granularity**: 30-second polling means wake-ups can be up to 30 seconds late. Fine for order supervision; not for real-time systems.
- **Single-process**: APScheduler shares the FastAPI process. Under heavy load, agent invocations could slow API responses. A separate worker process would fix this.
- **No authentication**: this is a single-tenant system with no auth layer.
- **Context compaction is naive**: the 20-entry sliding window works for demos but would need smarter summarization for orders with hundreds of events.
- **No idempotency on event injection**: duplicate events are possible if a client retries. An `event_id` deduplication check on `activity_log` would fix this.
- **Race condition on concurrent events**: two urgent events arriving simultaneously for the same run can trigger concurrent agent invocations. No locking exists at the run level.
