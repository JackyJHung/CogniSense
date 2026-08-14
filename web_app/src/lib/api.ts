export const BACKEND_URL =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(typeof body === "string" ? body : JSON.stringify(body));
    this.status = status;
    this.body = body;
  }
  /** FastAPI wraps custom error payloads inside { detail: ... }. */
  detail(): unknown {
    if (this.body && typeof this.body === "object" && "detail" in this.body) {
      return (this.body as { detail: unknown }).detail;
    }
    return this.body;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, parsed ?? text);
  return parsed as T;
}

function safeJson(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

/** Multipart upload — no Content-Type header, the browser sets the boundary. */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, { method: "POST", body: form });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, parsed ?? text);
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  postForm: <T>(path: string, form: FormData) => requestForm<T>(path, form),
};

// ---------- Types matching the FastAPI schemas ----------

export interface User {
  id: number;
  username: string;
  age: number;
  gender: string;
  race: string;
  wake_time: string;
  sleep_time: string;
  created_at: string;
}

export interface AssociationPresented {
  id: number;
  object_name: string;
  cue_word: string;
  image_path: string;
}

export interface MorningCheckin {
  id: number;
  timestamp: string;
  planned_activities: string;
  presented_associations: AssociationPresented[];
  disclaimer: string;
}

export interface MiddayCheckin {
  id: number;
  timestamp: string;
  what_user_has_done: string;
  planned_remainder: string | null;
  disclaimer: string;
}

export interface EveningCheckin {
  id: number;
  timestamp: string;
  activity_recall_accuracy: number | null;
  association_accuracy: number;
  avg_response_latency_ms: number | null;
  daily_cognitive_score: number | null;
  behavioral_biomarker_score: number | null;
  speech_biomarker_score: number | null;
  disclaimer: string;
}

export interface RiskComparison {
  user_recent_avg_score: number;
  /** 95% bootstrap interval on the recent average. null when there are too few
   *  scored days to estimate one — render that as "not enough data yet", never
   *  as a precise figure. */
  user_recent_avg_ci_low: number | null;
  user_recent_avg_ci_high: number | null;

  /** Change vs. the user's own earlier baseline, in percent, with its interval.
   *  The attention warning requires this interval to exclude zero. */
  trajectory_change_pct: number | null;
  trajectory_change_ci_low_pct: number | null;
  trajectory_change_ci_high_pct: number | null;
  n_scored_days: number;

  peer_expected_prevalence_pct: number;
  scd_peer_prevalence_pct: number;
  elevated_concern: boolean;
  concern_reason: string | null;

  /** Distinct from "no concern": the data cannot yet separate a real decline
   *  from normal day-to-day variation. Must be shown, not treated as an
   *  all-clear. */
  inconclusive: boolean;
  inconclusive_reason: string | null;

  suggestions: string[];
  citations: string[];
  disclaimer: string;
}

export interface DailySuggestions {
  suggestions: string[];
  lancet_risk_factor_source: string;
  disclaimer: string;
}

// ---------- Reminders / prospective memory ----------

export interface ReminderItem {
  id: number;
  description: string | null;
  label: string | null;
  image_path: string | null;
  due_at: string | null;
  status: string;
  created_at: string;
  completed_at: string | null;
}

/** The prompt. Carries no item text on purpose — that is the test. */
export interface ReminderCheck {
  check_id: number;
  triggered_at: string;
  n_items_active: number;
  prompt: string;
  disclaimer: string;
}

export interface ItemMatch {
  item_id: number;
  overlap: number;
  matched: boolean;
}

export interface ReminderRecallResult {
  check_id: number;
  n_active: number;
  n_recalled: number;
  passed: boolean;
  prospective_score: number;
  feedback: string;
  matches: ItemMatch[];
  /** Always populated, pass or fail. The aid is never withheld. */
  items: ReminderItem[];
  disclaimer: string;
  memory_aid_disclaimer: string;
}

export interface ProspectiveScore {
  n_checks: number;
  recall_rate: number | null;
  recall_rate_ci_low: number | null;
  recall_rate_ci_high: number | null;
  change_pct: number | null;
  change_ci_low_pct: number | null;
  change_ci_high_pct: number | null;
  trend_available: boolean;
  trend_note: string | null;
  memory_aid_disclaimer: string;
}

export { ApiError };
