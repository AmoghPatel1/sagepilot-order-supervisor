"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import api, { Run, parseUTC } from "../lib/api";

const STATUS_COLORS: Record<string, string> = {
  running: "bg-blue-500",
  sleeping: "bg-yellow-500",
  interrupted: "bg-orange-500",
  completed: "bg-green-500",
  terminated: "bg-red-500",
};

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  async function fetchRuns() {
    try {
      const res = await api.get("/api/runs");
      setRuns(res.data);
    } finally {
      setLoading(false);
    }
  }

  const active = runs.filter(
    (r) => !["completed", "terminated"].includes(r.status),
  );
  const finished = runs.filter((r) =>
    ["completed", "terminated"].includes(r.status),
  );

  if (loading)
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
        Loading...
      </div>
    );

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link
              href="/"
              className="text-gray-400 hover:text-white text-sm mb-2 block"
            >
              ← Home
            </Link>
            <h1 className="text-2xl font-bold">Runs</h1>
          </div>
          <Link
            href="/runs/new"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium"
          >
            + New Run
          </Link>
        </div>

        {active.length > 0 && (
          <div className="mb-8">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
              Active ({active.length})
            </h2>
            <div className="space-y-3">
              {active.map((run) => (
                <RunCard key={run.id} run={run} />
              ))}
            </div>
          </div>
        )}

        {finished.length > 0 && (
          <div>
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
              Completed ({finished.length})
            </h2>
            <div className="space-y-3">
              {finished.map((run) => (
                <RunCard key={run.id} run={run} />
              ))}
            </div>
          </div>
        )}

        {runs.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            No runs yet.{" "}
            <Link
              href="/runs/new"
              className="text-blue-400 hover:text-blue-300"
            >
              Start one →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function RunCard({ run }: { run: Run }) {
  return (
    <Link href={`/runs/${run.id}`}>
      <div className="bg-gray-900 border border-gray-800 hover:border-gray-600 rounded-lg p-4 transition-colors">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-2 h-2 rounded-full ${STATUS_COLORS[run.status] || "bg-gray-500"}`}
            />
            <span className="font-medium">{run.order_id}</span>
            <span className="text-xs text-gray-500 capitalize">
              {run.status}
            </span>
          </div>
          <span className="text-xs text-gray-500">
            {parseUTC(run.created_at).toLocaleString()}
          </span>
        </div>
        {run.state_summary && (
          <p className="text-sm text-gray-400 mt-2 ml-5 line-clamp-1">
            {run.state_summary}
          </p>
        )}
        {run.wake_at && run.status === "sleeping" && (
          <p className="text-xs text-yellow-500 mt-1 ml-5">
            Wakes at {parseUTC(run.wake_at).toLocaleTimeString()}
          </p>
        )}
      </div>
    </Link>
  );
}
