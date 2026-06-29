# Design Note

## The Core Design Challenge

This system does two things that pull in opposite directions: it must be simple enough to run on minimal infrastructure, and it must be designed well enough that every decision can be defended under scrutiny. This note explains the reasoning behind each major decision — not what was built, but why.

---

## Orchestration: Why DB State + APScheduler

Orchestration was an open choice. The real options were Temporal, a queue-based system (Redis + Celery), or database state with a scheduler.

**Temporal** is the correct production answer for this problem. It provides durable execution, built-in sleep/wake primitives (`workflow.sleep()`), automatic crash recovery through event sourcing and replay, and a visibility UI that gives operators full execution history. At a company processing millions of events per day, Temporal is not optional — it is the only approach that handles failure, scale, and observability together.

However, Temporal requires running a separate server process, configuring namespaces, and writing workflow code in its SDK. For this scope, that infrastructure cost outweighs the benefit — time better spent on the agent logic itself.

**The key insight** is that database state + a scheduler achieves the same logical model as Temporal's primitives for a single-machine deployment:

| Temporal concept | This implementation |
|---|---|
| `workflow.sleep(duration)` | `wake_at = now + duration, status = sleeping` |
| Durable timer | APScheduler polls `WHERE status='sleeping' AND wake_at <= now` |
| Signal | `POST /runs/{id}/events` that wakes a sleeping run |
| Workflow state | `state_summary` + `activity_log` in PostgreSQL |
| Worker crash recovery | Background job resets stuck `running` runs to `sleeping` |

The difference is failure handling under load. Temporal replays from a checkpoint; this system relies on a crash recovery job and loses the in-flight LLM call. For a single-machine deployment running one order at a time, this is an acceptable and explicit tradeoff. For production at scale, Temporal is the answer — and the migration path is a direct mapping.

**Why not Redis + Celery?** Celery is designed for short, discrete tasks. An agent run is long-lived and stateful — it needs to read history, update state, and schedule its own next wake-up. That state lives outside the task regardless, which means Celery adds infrastructure without simplifying the problem. The queue is not the hard part; the state management is.

---

## Agent Design: Why Direct SDK Over LangChain

LangChain abstracts three things: tool calling, memory, and chains. In this system,
all three are handled explicitly:

- **Tool calling** — the Anthropic SDK returns `tool_use` blocks; we execute them
  in a simple dispatch function
- **Memory** — the `state_summary` field, updated by the agent calling
  `update_state_summary` on every cycle
- **Chains** — sequential tool calls within a single LLM response; there is no
  multi-step chain abstraction needed

Adding LangChain would abstract these without simplifying them. The cost is
debugging difficulty — when something goes wrong in a LangChain agent, the
failure is often inside the framework rather than in application code. Direct
SDK usage means every step is a Python function call that can be logged, tested,
and traced without framework indirection.

This was a deliberate choice, not a shortcut. Transparency in the agent's execution
path matters more than convenience at this scope.

---

## Tool Design: Why 8 Flat Tools

The agent has 8 tools — 5 business actions and 3 runtime controls. A more
sophisticated design might use sub-agents: a payments agent, a logistics agent,
a customer communications agent, each with a narrower tool set and tighter prompt.

The flat single-agent design was chosen for two reasons. First, the action space
is small enough that one agent handles it without context confusion. Second,
sub-agent coordination adds complexity — the routing layer, handoff protocols,
and shared state management — that isn't justified when the problem fits cleanly
in a single context window.

The migration path to sub-agents is clear: extract tool subsets into specialized
agent functions, add a router that classifies order state and delegates. That's
an extension, not a rewrite.

**Why business actions are stubs** — the execution layer is intentionally separated
from the decision layer. The agent decides what to do; the tool implementation
does it. Real integrations mean changing only the tool implementation functions,
not the agent logic or prompt.

---

## State and Memory: Why Structured JSON Summary

The original design used a free-text `summary` field. This was replaced with a
structured JSON schema requiring six fields: `current_order_status`,
`last_action_taken`, `open_issues`, `next_expected_event`, `risk_level`, and `notes`.

The problem with free text is twofold. First, there is no way to detect a bad
summary — if the agent writes something vague, the next cycle reasons from a
degraded context without any signal that something is wrong. Second, free text
is unqueryable — you cannot find all runs at `risk_level: high` or filter by
open issues.

The structured schema enforces completeness at write time. Missing fields are
rejected and logged. The agent receives the error as a tool result and retries.
The run's state is only updated on a validated write.

The tradeoff is that the agent must now fill six fields correctly every cycle.
This is more work for the model, but it is the right tradeoff — correctness of
the memory system is more important than ease of writing it.

**Why agent-authored memory at all, rather than system-derived?** Because the
agent knows what is meaningful. A system-derived summary would either dump the
raw log (too long) or apply a fixed compression rule (too rigid). The agent can
write a summary that reflects its actual reasoning priorities — which events
matter, which issues are open, what it's watching for next. The cost is that
the summary quality depends on the model's judgment. The structured schema
mitigates the worst failure modes of that dependency.

---

## Event Handling: Why a Pure Python Classifier

Every incoming event passes through a classifier before the agent is invoked.
The classifier is a hardcoded Python dictionary — no LLM call, no network
request, no latency.

The alternative would be asking the main agent to decide urgency, or using a
secondary LLM call. Both are wrong for this use case. Urgency classification
happens on every event injection. At production scale — millions of events per
day — an LLM call per event would be prohibitively expensive and slow. A
deterministic rule is cheaper, faster, and more predictable.

The weakness is rigidity: unknown event types fall back to urgent by default,
and new event types require a code change to classify correctly. The default-to-urgent
policy is a deliberate choice — missing a critical event is more costly than an
unnecessary agent wake.

Per-run classifier guidance (where the agent writes event-urgency hints after
each cycle) was considered but not implemented — the static classifier covers
all current event types and the added complexity wasn't justified at this scope.

---

## Crash Recovery: Why a Background Job

The scheduler runs a crash recovery job every 5 minutes. It finds runs stuck in
`running` status for longer than a configurable timeout and resets them to
`sleeping`. A run stuck in `running` is the signature of a server crash
mid-invocation — the LLM call was in flight when the process died.

The alternative approaches were: do nothing (acceptable for a demo, wrong for
any real deployment), or use Temporal which handles this natively. Since we're
not using Temporal, a recovery job is the right compensating control.

The known gap in this approach is idempotency. If the agent completed some tool
calls before the crash, those writes are already in `activity_log`. On retry,
the agent may take the same actions again. Full idempotency requires comparing
the current cycle's intended tool calls against existing log entries before
executing — not implemented here, but the correct production fix.

---

## What I Would Do Differently at Production Scale

At production scale with high event volume, several things break in this design:

**Temporal replaces APScheduler entirely.** The DB polling pattern works at low
volume but cannot handle the throughput or provide the durability guarantees
needed at scale. The migration is a direct mapping — runs become workflows,
tools become activities, `POST /events` becomes signals.

**Event ingestion decouples from agent invocation.** Currently, an urgent event
triggers an inline agent invocation. At high volume, this means LLM calls happen
in the request path. The correct architecture queues events and processes them
through a worker pool, completely decoupled from HTTP request handling.

**The activity_log table needs partitioning.** A single unpartitioned table
absorbing millions of inserts degrades quickly. Partitioning by `run_id` range
or by time, with a GIN index on the JSONB `payload` column for payload-level
queries, is the production path.

**The single-agent flat design gets a routing layer.** As the action space grows
and order types diversify, a single agent's context gets bloated and its judgment
gets noisier. Specialized sub-agents with domain-specific prompts and tool sets,
orchestrated by a routing layer, is the right architecture at scale.

---

## Summary of Key Tradeoffs

| Decision | Chosen | Alternative | Why chosen |
|---|---|---|---|
| Orchestration | DB + APScheduler | Temporal | Setup cost vs. correctness at this scope |
| LLM framework | Direct Anthropic SDK | LangChain | Transparency and debuggability |
| Agent structure | Single flat agent | Sub-agent hierarchy | Complexity not justified at this action space size |
| Memory format | Structured JSON | Free text | Enforces completeness, enables validation |
| Event classifier | Pure Python rules | LLM call | Cost, latency, determinism |
| Business actions | Stubs (DB writes only) | Real integrations | Clean separation of decision vs execution |
| Crash recovery | Background scheduler job | Temporal replay | Compensating control for not using Temporal |
