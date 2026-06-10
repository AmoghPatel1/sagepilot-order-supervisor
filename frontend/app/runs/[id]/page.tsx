"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import api, { Run, ActivityEntry, getRunStats, parseUTC } from "../../lib/api";

const ENTRY_COLORS: Record<string, string> = {
  event: "border-blue-500 bg-blue-500/10",
  agent_action: "border-green-500 bg-green-500/10",
  wake_decision: "border-yellow-500 bg-yellow-500/10",
  sleep_decision: "border-gray-500 bg-gray-500/10",
  instruction: "border-purple-500 bg-purple-500/10",
  reasoning: "border-cyan-500 bg-cyan-500/10",
  final_output: "border-orange-500 bg-orange-500/10",
};

const ENTRY_LABELS: Record<string, string> = {
  event: "Event",
  agent_action: "Action",
  wake_decision: "Woke Up",
  sleep_decision: "Sleeping",
  instruction: "Instruction",
  reasoning: "Reasoning",
  final_output: "Final Output",
};

const EVENT_TYPES = [
  "payment_confirmed",
  "payment_failed",
  "shipment_created",
  "shipment_delayed",
  "delivered",
  "refund_requested",
  "customer_message_received",
  "no_update_for_n_hours",
];

export default function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<Run | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [eventType, setEventType] = useState("payment_confirmed");
  const [eventPayload, setEventPayload] = useState("");
  const [instruction, setInstruction] = useState("");
  const [activeTab, setActiveTab] = useState<
    "activity" | "state" | "summary" | "stats"
  >("activity");
  const [stats, setStats] = useState<any>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const fetchData = useCallback(async () => {
    const [runRes, actRes] = await Promise.all([
      api.get(`/api/runs/${id}`),
      api.get(`/api/runs/${id}/activity`),
    ]);
    setRun(runRes.data);
    setActivity(actRes.data);
  }, [id]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (activeTab !== "stats" || !run) return;
    setStatsLoading(true);
    getRunStats(run.id)
      .then(setStats)
      .catch(console.error)
      .finally(() => setStatsLoading(false));
  }, [activeTab, run?.id]);

  async function injectEvent() {
    let payload = {};
    try {
      payload = eventPayload ? JSON.parse(eventPayload) : {};
    } catch {}
    await api.post(`/api/runs/${id}/events`, {
      event_type: eventType,
      payload,
    });
    setEventPayload("");
    fetchData();
  }

  async function addInstruction() {
    if (!instruction.trim()) return;
    await api.post(`/api/runs/${id}/instructions`, { instruction });
    setInstruction("");
    fetchData();
  }

  async function runAction(action: string) {
    await api.post(`/api/runs/${id}/${action}`);
    fetchData();
  }

  if (!run)
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
        Loading...
      </div>
    );

  const isFinished = ["completed", "terminated"].includes(run.status);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <Link
            href="/runs"
            className="text-gray-400 hover:text-white text-sm mb-2 block"
          >
            ← Back to Runs
          </Link>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">{run.order_id}</h1>
              <div className="flex items-center gap-3 mt-1">
                <StatusBadge status={run.status} />
                <span className="text-xs text-gray-500">
                  Started {parseUTC(run.created_at).toLocaleString()}
                </span>
                {run.wake_at && run.status === "sleeping" && (
                  <span className="text-xs text-yellow-400">
                    Wakes {parseUTC(run.wake_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>

            {/* Controls */}
            {!isFinished && (
              <div className="flex gap-2">
                {run.status === "interrupted" ? (
                  <button
                    onClick={() => runAction("resume")}
                    className="px-3 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm"
                  >
                    Resume
                  </button>
                ) : (
                  <button
                    onClick={() => runAction("interrupt")}
                    className="px-3 py-1.5 bg-orange-700 hover:bg-orange-600 rounded text-sm"
                  >
                    Pause
                  </button>
                )}
                <button
                  onClick={() => runAction("terminate")}
                  className="px-3 py-1.5 bg-red-700 hover:bg-red-600 rounded text-sm"
                >
                  Terminate
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6">
          {/* Left: Activity + State + Summary tabs */}
          <div className="col-span-2">
            <div className="flex gap-1 mb-4 bg-gray-900 rounded-lg p-1 w-fit">
              {(["activity", "state", "summary", "stats"] as const).map(
                (tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-1.5 rounded text-sm font-medium transition-colors capitalize ${
                      activeTab === tab
                        ? "bg-gray-700 text-white"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    {tab}
                  </button>
                ),
              )}
            </div>

            {activeTab === "activity" && (
              <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
                {activity.length === 0 && (
                  <p className="text-gray-500 text-sm">No activity yet...</p>
                )}
                {activity.map((entry) => (
                  <ActivityCard key={entry.id} entry={entry} />
                ))}
              </div>
            )}

            {activeTab === "state" && (
              <div className="space-y-4">
                {(() => {
                  const summary = parseStateSummary(run?.state_summary);

                  if (!summary) {
                    return (
                      <p className="text-gray-400 text-sm">
                        No state summary yet. The agent will write one after its
                        first cycle.
                      </p>
                    );
                  }

                  // Legacy free-text fallback
                  if (summary._raw) {
                    return (
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-yellow-400 mb-2">
                          Legacy format
                        </p>
                        <p className="text-sm text-gray-300 whitespace-pre-wrap">
                          {summary._raw}
                        </p>
                      </div>
                    );
                  }

                  // Structured summary
                  return (
                    <>
                      {/* Header row: order status + risk level */}
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 bg-gray-800 rounded-lg p-4">
                          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                            Order Status
                          </p>
                          <p className="text-sm text-white font-medium">
                            {summary.current_order_status || "—"}
                          </p>
                        </div>
                        <div className="bg-gray-800 rounded-lg p-4 min-w-[120px] text-center">
                          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                            Risk Level
                          </p>
                          <span
                            className={`inline-block text-xs font-semibold px-3 py-1 rounded-full ${riskBadge(
                              summary.risk_level,
                            )}`}
                          >
                            {summary.risk_level?.toUpperCase() || "—"}
                          </span>
                        </div>
                      </div>

                      {/* Last action */}
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                          Last Action Taken
                        </p>
                        <p className="text-sm text-gray-300">
                          {summary.last_action_taken || "None"}
                        </p>
                      </div>

                      {/* Open issues */}
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                          Open Issues
                        </p>
                        {summary.open_issues &&
                        summary.open_issues.length > 0 ? (
                          <ul className="space-y-1">
                            {summary.open_issues.map(
                              (issue: string, i: number) => (
                                <li
                                  key={i}
                                  className="flex items-start gap-2 text-sm text-red-300"
                                >
                                  <span className="mt-0.5 text-red-500">●</span>
                                  {issue}
                                </li>
                              ),
                            )}
                          </ul>
                        ) : (
                          <p className="text-sm text-green-400">None</p>
                        )}
                      </div>

                      {/* Next expected event */}
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                          Next Expected Event
                        </p>
                        <p className="text-sm text-blue-300">
                          {summary.next_expected_event || "—"}
                        </p>
                      </div>

                      {/* Notes */}
                      {summary.notes && (
                        <div className="bg-gray-800 rounded-lg p-4">
                          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                            Agent Notes
                          </p>
                          <p className="text-sm text-gray-300 whitespace-pre-wrap">
                            {summary.notes}
                          </p>
                        </div>
                      )}

                      {/* Last updated */}
                      {summary.updated_at && (
                        <p className="text-xs text-gray-600 text-right">
                          Last updated:{" "}
                          {parseUTC(summary.updated_at).toLocaleTimeString()}
                        </p>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            {activeTab === "summary" && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                {run.final_output ? (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-1">
                        Final Summary
                      </h3>
                      <p className="text-sm text-gray-300">
                        {run.final_output.final_summary}
                      </p>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-1">
                        Key Actions Taken
                      </h3>
                      <p className="text-sm text-gray-300">
                        {run.final_output.key_actions}
                      </p>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-1">
                        Learnings
                      </h3>
                      <p className="text-sm text-gray-300">
                        {run.final_output.learnings}
                      </p>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-1">
                        Completion Reason
                      </h3>
                      <p className="text-sm text-gray-300">
                        {run.final_output.reason}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">
                    No summary yet. Available after run completes.
                  </p>
                )}
              </div>
            )}

            {activeTab === "stats" && (
              <div className="space-y-4">
                {statsLoading ? (
                  <p className="text-gray-400 text-sm">Loading stats...</p>
                ) : !stats ? (
                  <p className="text-gray-400 text-sm">
                    No stats available yet.
                  </p>
                ) : (
                  <>
                    {/* Top-line numbers */}
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {[
                        { label: "Agent Cycles", value: stats.total_cycles },
                        { label: "Actions Taken", value: stats.total_actions },
                        {
                          label: "Events Received",
                          value: stats.total_events_received,
                        },
                        {
                          label: "Instructions Added",
                          value: stats.instructions_added,
                        },
                      ].map(({ label, value }) => (
                        <div
                          key={label}
                          className="bg-gray-800 rounded-lg p-4 text-center"
                        >
                          <p className="text-2xl font-bold text-white">
                            {value}
                          </p>
                          <p className="text-xs text-gray-400 mt-1">{label}</p>
                        </div>
                      ))}
                    </div>

                    {/* Risk level banner — only if run is active */}
                    {stats.status !== "completed" &&
                      stats.status !== "terminated" && (
                        <div
                          className={`rounded-lg p-3 flex items-center justify-between ${
                            stats.current_risk_level === "high"
                              ? "bg-red-900/40 border border-red-700"
                              : stats.current_risk_level === "medium"
                                ? "bg-yellow-900/40 border border-yellow-700"
                                : "bg-green-900/40 border border-green-700"
                          }`}
                        >
                          <span className="text-sm text-gray-300">
                            Current Risk Level
                          </span>
                          <span
                            className={`text-sm font-semibold uppercase ${
                              stats.current_risk_level === "high"
                                ? "text-red-300"
                                : stats.current_risk_level === "medium"
                                  ? "text-yellow-300"
                                  : "text-green-300"
                            }`}
                          >
                            {stats.current_risk_level} —{" "}
                            {stats.open_issues_count} open issue
                            {stats.open_issues_count !== 1 ? "s" : ""}
                          </span>
                        </div>
                      )}

                    {/* Time distribution */}
                    <div className="bg-gray-800 rounded-lg p-4">
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                        Time Distribution
                      </p>
                      <div className="flex gap-1 h-4 rounded overflow-hidden mb-2">
                        <div
                          className="bg-blue-600"
                          style={{
                            width: `${100 - (stats.time.sleep_percentage || 0)}%`,
                          }}
                          title={`Active: ${stats.time.active_minutes}m`}
                        />
                        <div
                          className="bg-gray-600"
                          style={{
                            width: `${stats.time.sleep_percentage || 0}%`,
                          }}
                          title={`Sleeping: ${stats.time.sleeping_minutes}m`}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>
                          <span className="inline-block w-2 h-2 bg-blue-600 rounded-sm mr-1" />
                          Active {stats.time.active_minutes}m (
                          {Math.round(100 - (stats.time.sleep_percentage || 0))}
                          %)
                        </span>
                        <span>
                          <span className="inline-block w-2 h-2 bg-gray-600 rounded-sm mr-1" />
                          Sleeping {stats.time.sleeping_minutes}m (
                          {stats.time.sleep_percentage}%)
                        </span>
                      </div>
                    </div>

                    {/* Wake triggers */}
                    {Object.keys(stats.wake_triggers).length > 0 && (
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                          Wake Triggers
                        </p>
                        <div className="space-y-2">
                          {Object.entries(stats.wake_triggers).map(
                            ([trigger, count]) => (
                              <div
                                key={trigger}
                                className="flex justify-between text-sm"
                              >
                                <span className="text-gray-300 capitalize">
                                  {trigger.replace(/_/g, " ")}
                                </span>
                                <span className="text-white font-medium">
                                  {count as number}
                                </span>
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    )}

                    {/* Actions by type */}
                    {Object.keys(stats.actions_by_type).length > 0 && (
                      <div className="bg-gray-800 rounded-lg p-4">
                        <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                          Actions by Type
                        </p>
                        <div className="space-y-2">
                          {Object.entries(stats.actions_by_type).map(
                            ([action, count]) => (
                              <div
                                key={action}
                                className="flex justify-between text-sm"
                              >
                                <span className="text-gray-300">
                                  {action.replace(/_/g, " ")}
                                </span>
                                <span className="text-white font-medium">
                                  {count as number}
                                </span>
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    )}

                    {/* Token estimate */}
                    <div className="bg-gray-800 rounded-lg p-4">
                      <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">
                        Estimated Token Usage
                      </p>
                      <div className="space-y-2">
                        {[
                          {
                            label: "Input tokens",
                            value:
                              stats.tokens.estimated_input.toLocaleString(),
                          },
                          {
                            label: "Output tokens",
                            value:
                              stats.tokens.estimated_output.toLocaleString(),
                          },
                          {
                            label: "Total",
                            value:
                              stats.tokens.estimated_total.toLocaleString(),
                          },
                        ].map(({ label, value }) => (
                          <div
                            key={label}
                            className="flex justify-between text-sm"
                          >
                            <span className="text-gray-400">{label}</span>
                            <span className="text-white font-mono">
                              {value}
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-gray-600 mt-3">
                        {stats.tokens.note}
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Right: Controls panel */}
          <div className="space-y-4">
            {/* Inject Event */}
            {!isFinished && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm font-medium mb-3">Inject Event</h3>
                <select
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm mb-2"
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                >
                  {EVENT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm mb-2 font-mono"
                  value={eventPayload}
                  onChange={(e) => setEventPayload(e.target.value)}
                  placeholder='{"key": "value"} (optional)'
                />
                <button
                  onClick={injectEvent}
                  className="w-full py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
                >
                  Send Event
                </button>
              </div>
            )}

            {/* Add Instruction */}
            {!isFinished && (
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm font-medium mb-3">Add Instruction</h3>
                <textarea
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm mb-2 h-20"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="e.g. Escalate immediately if delayed"
                />
                <button
                  onClick={addInstruction}
                  className="w-full py-1.5 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium"
                >
                  Add Instruction
                </button>
              </div>
            )}

            {/* Run stats */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-medium mb-3 text-gray-400">
                Run Stats
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Total events</span>
                  <span>
                    {activity.filter((a) => a.entry_type === "event").length}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Agent actions</span>
                  <span>
                    {
                      activity.filter((a) => a.entry_type === "agent_action")
                        .length
                    }
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Wake-ups</span>
                  <span>
                    {
                      activity.filter((a) => a.entry_type === "wake_decision")
                        .length
                    }
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Sleep cycles</span>
                  <span>
                    {
                      activity.filter((a) => a.entry_type === "sleep_decision")
                        .length
                    }
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function parseStateSummary(raw: string | null | undefined) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null) return parsed;
  } catch {
    // Legacy free-text summary
  }
  return { _raw: raw };
}

// Risk level badge colors
function riskBadge(level: string) {
  const map: Record<string, string> = {
    low: "bg-green-900 text-green-300",
    medium: "bg-yellow-900 text-yellow-300",
    high: "bg-red-900 text-red-300",
  };
  return map[level] ?? "bg-gray-700 text-gray-300";
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    sleeping: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    interrupted: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    completed: "bg-green-500/20 text-green-400 border-green-500/30",
    terminated: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded border capitalize ${colors[status] || ""}`}
    >
      {status}
    </span>
  );
}

function ActivityCard({ entry }: { entry: ActivityEntry }) {
  const [expanded, setExpanded] = useState(false);
  const colorClass =
    ENTRY_COLORS[entry.entry_type] || "border-gray-700 bg-gray-800";
  const label = ENTRY_LABELS[entry.entry_type] || entry.entry_type;

  function renderPayload() {
    const p = entry.payload;
    if (entry.entry_type === "event") {
      return (
        <span>
          {p.event_type}
          {p.data && Object.keys(p.data).length > 0
            ? ` — ${JSON.stringify(p.data)}`
            : ""}
        </span>
      );
    }
    if (entry.entry_type === "agent_action") {
      return (
        <span>
          {p.action?.replace(/_/g, " ")} — {p.message || p.note || ""}
        </span>
      );
    }
    if (entry.entry_type === "sleep_decision") {
      return (
        <span>
          {p.reason} (wake at{" "}
          {p.wake_at ? parseUTC(p.wake_at).toLocaleTimeString() : "?"}
        </span>
      );
    }
    if (entry.entry_type === "wake_decision") {
      return <span>Triggered by: {p.trigger}</span>;
    }
    if (entry.entry_type === "reasoning") {
      const text = p.summary as string;
      return (
        <div>
          <span className={expanded ? undefined : "line-clamp-2"}>{text}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            className="mt-1 text-xs text-cyan-400 hover:text-cyan-300 font-medium block"
          >
            {expanded ? "Show less ↑" : "Show more ↓"}
          </button>
        </div>
      );
    }
    if (entry.entry_type === "instruction") {
      return <span>{p.instruction || p.action}</span>;
    }
    if (entry.entry_type === "final_output") {
      return <span>{p.reason}</span>;
    }
    return (
      <span className="font-mono text-xs">
        {JSON.stringify(p).slice(0, 100)}
      </span>
    );
  }

  return (
    <div className={`border-l-2 rounded-r-lg px-3 py-2 ${colorClass}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium uppercase tracking-wider opacity-70">
          {label}
        </span>
        <span className="text-xs text-gray-500">
          {parseUTC(entry.created_at).toLocaleTimeString()}
        </span>
      </div>
      <div className="text-sm text-gray-300">{renderPayload()}</div>
    </div>
  );
}
