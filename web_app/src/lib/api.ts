/* Same-origin by default: "/api" is proxied to the backend in development (see
 * vite.config.ts) and served by the backend itself in production. That is a
 * requirement, not a convenience -- the session cookie is SameSite=Strict, so a
 * cross-origin API base would mean the browser never sends it. */
export const BACKEND_URL =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "/api";

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

/* ---------- session transport ----------
 *
 * The session token is NOT held here any more. It lives in an HttpOnly cookie
 * that JavaScript cannot read, so an XSS on this origin can no longer walk away
 * with a 30-day credential. The browser attaches it automatically; every request
 * just needs `credentials: "include"`.
 *
 * The price of an auto-attached cookie is CSRF, paid for with a double-submit
 * token: the backend also sets a READABLE cookie, and we echo it back in a
 * header. An attacking origin can make the browser send cookies but cannot read
 * them, so it cannot produce the header.
 *
 * Legacy note: an older build kept the token in localStorage. Any leftover copy
 * is cleared on load so it cannot linger as a stealable credential.
 */
const LEGACY_TOKEN_KEY = "cognisense.token";
if (typeof localStorage !== "undefined") localStorage.removeItem(LEGACY_TOKEN_KEY);

const CSRF_COOKIE = "cognisense_csrf";

function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

/* Called when the server rejects our token, so the app can drop to the login
 * screen instead of rendering empty pages and confusing errors. Registered by
 * AuthProvider; a plain callback because api.ts must stay outside React. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

function buildHeaders(method: string, hasBody: boolean): Record<string, string> {
  const headers: Record<string, string> = {};
  if (hasBody) headers["Content-Type"] = "application/json";

  // Double-submit CSRF token on state-changing methods only; safe methods are
  // exempt on the server too.
  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  return headers;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers: buildHeaders(method, body !== undefined),
    // Without this the browser omits the session cookie entirely.
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (res.status === 401) {
    // The session is gone, expired, or was revoked elsewhere.
    onUnauthorized?.();
  }
  if (!res.ok) throw new ApiError(res.status, parsed ?? text);
  return parsed as T;
}

function safeJson(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

/** Multipart upload — no Content-Type header, the browser sets the boundary. */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: buildHeaders("POST", false),
    credentials: "include",
    body: form,
  });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (res.status === 401) {
    onUnauthorized?.();
  }
  if (!res.ok) throw new ApiError(res.status, parsed ?? text);
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  postForm: <T>(path: string, form: FormData) => requestForm<T>(path, form),
};

// ---------- Types matching the FastAPI schemas ----------

/** What /users/login and /users/signup return. `token` is shown exactly once. */
export interface AuthResult {
  user: User;
  token: string;
  token_type: string;
  expires_at: string;
}

export interface RecoveryCodes {
  codes: string[];
  generated: number;
  warning: string;
}

export interface RecoveryStatus {
  codes_remaining: number;
  codes_used: number;
  has_codes: boolean;
  email: string | null;
  email_verified: boolean;
  /** False when the server has no SMTP configured — never tell the user to
   *  check an inbox that will stay empty. */
  email_delivery_enabled: boolean;
}

export interface GenericMessage {
  ok: boolean;
  message: string;
}

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
