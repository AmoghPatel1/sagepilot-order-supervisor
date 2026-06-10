"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import api, { Supervisor } from "../../lib/api";

function NewRunForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [form, setForm] = useState({
    supervisor_id: searchParams.get("supervisor_id") || "",
    order_id: `ORDER-${Date.now().toString().slice(-6)}`,
    additional_instructions: "",
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/api/supervisors").then(r => setSupervisors(r.data));
  }, []);

  async function submit() {
    if (!form.supervisor_id || !form.order_id) return;
    setLoading(true);
    try {
      const res = await api.post("/api/runs", form);
      router.push(`/runs/${res.data.id}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-2xl mx-auto">
        <Link href="/runs" className="text-gray-400 hover:text-white text-sm mb-6 block">
          ← Back to Runs
        </Link>
        <h1 className="text-2xl font-bold mb-8">Start New Run</h1>

        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-6">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Supervisor Template</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2"
              value={form.supervisor_id}
              onChange={e => setForm({ ...form, supervisor_id: e.target.value })}
            >
              <option value="">Select a supervisor...</option>
              {supervisors.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">Order ID</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2"
              value={form.order_id}
              onChange={e => setForm({ ...form, order_id: e.target.value })}
              placeholder="ORDER-001"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Initial Instructions <span className="text-gray-600">(optional)</span>
            </label>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 h-24 text-sm"
              value={form.additional_instructions}
              onChange={e => setForm({ ...form, additional_instructions: e.target.value })}
              placeholder="e.g. Prioritize speed over cost. Escalate immediately if shipment is delayed."
            />
          </div>

          <button
            onClick={submit}
            disabled={loading || !form.supervisor_id || !form.order_id}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
          >
            {loading ? "Starting..." : "Start Run"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function NewRunPage() {
  return (
    <Suspense>
      <NewRunForm />
    </Suspense>
  );
}