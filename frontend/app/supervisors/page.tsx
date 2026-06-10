"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import api, { Supervisor } from "../lib/api";

export default function SupervisorsPage() {
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    base_instruction: "",
    default_wake_interval_minutes: 2,
    wake_aggressiveness: "normal",
    model: "claude-haiku-4-5-20251001",
  });

  useEffect(() => {
    fetchSupervisors();
  }, []);

  async function fetchSupervisors() {
    try {
      const res = await api.get("/api/supervisors");
      setSupervisors(res.data);
    } finally {
      setLoading(false);
    }
  }

  async function createSupervisor() {
    if (!form.name || !form.base_instruction) return;
    await api.post("/api/supervisors", form);
    setShowForm(false);
    setForm({
      name: "",
      base_instruction: "",
      default_wake_interval_minutes: 2,
      wake_aggressiveness: "normal",
      model: "claude-haiku-4-5-20251001",
    });
    fetchSupervisors();
  }

  if (loading) return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      Loading...
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link href="/" className="text-gray-400 hover:text-white text-sm mb-2 block">
              ← Home
            </Link>
            <h1 className="text-2xl font-bold">Supervisors</h1>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium"
          >
            + New Supervisor
          </button>
        </div>

        {showForm && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 mb-6">
            <h2 className="text-lg font-semibold mb-4">Create Supervisor</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Name</label>
                <input
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Standard Order Supervisor"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Base Instruction</label>
                <textarea
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm h-32"
                  value={form.base_instruction}
                  onChange={e => setForm({ ...form, base_instruction: e.target.value })}
                  placeholder="You are an AI supervisor monitoring an e-commerce order..."
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Wake Interval (min)</label>
                  <input
                    type="number"
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={form.default_wake_interval_minutes}
                    onChange={e => setForm({ ...form, default_wake_interval_minutes: parseInt(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Aggressiveness</label>
                  <select
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={form.wake_aggressiveness}
                    onChange={e => setForm({ ...form, wake_aggressiveness: e.target.value })}
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Model</label>
                  <select
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={form.model}
                    onChange={e => setForm({ ...form, model: e.target.value })}
                  >
                    <option value="claude-haiku-4-5-20251001">Claude Haiku (fast)</option>
                    <option value="claude-sonnet-4-5">Claude Sonnet (smart)</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={createSupervisor}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium"
                >
                  Create
                </button>
                <button
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-4">
          {supervisors.map(s => (
            <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{s.name}</h3>
                  <p className="text-gray-400 text-sm mt-1 max-w-2xl">{s.base_instruction}</p>
                </div>
                <span className="text-xs bg-gray-800 px-2 py-1 rounded text-gray-400">
                  {s.model}
                </span>
              </div>
              <div className="mt-4 flex gap-4 text-xs text-gray-500">
                <span>Wake every {s.default_wake_interval_minutes}m</span>
                <span>Aggressiveness: {s.wake_aggressiveness}</span>
                <span>{s.available_actions.length} actions available</span>
              </div>
              <div className="mt-3">
                <Link
                  href={`/runs/new?supervisor_id=${s.id}`}
                  className="text-sm text-blue-400 hover:text-blue-300"
                >
                  Start a run with this supervisor →
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}