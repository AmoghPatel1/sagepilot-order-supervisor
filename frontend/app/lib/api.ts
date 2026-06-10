import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
});

export default api;

// Types
export interface Supervisor {
  id: string;
  name: string;
  base_instruction: string;
  available_actions: string[];
  default_wake_interval_minutes: number;
  wake_aggressiveness: string;
  model: string;
  created_at: string;
}

export interface Run {
  id: string;
  supervisor_id: string;
  order_id: string;
  status: string;
  wake_at: string | null;
  state_summary: string;
  additional_instructions: string;
  final_output: {
    reason: string;
    final_summary: string;
    key_actions: string;
    learnings: string;
  } | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ActivityEntry {
  id: string;
  run_id: string;
  entry_type: string;
  payload: any;
  created_at: string;
}

export async function getRunStats(runId: string) {
  const res = await api.get(`/api/runs/${runId}/stats`);
  return res.data;
}

/**
 * Parse a timestamp string as UTC (even if it lacks timezone info)
 * and return a Date object in the user's local timezone.
 */
export function parseUTC(ts: string): Date {
  if (!ts) return new Date(NaN);
  if (ts.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(ts)) {
    return new Date(ts);
  }
  return new Date(ts + "Z");
}
