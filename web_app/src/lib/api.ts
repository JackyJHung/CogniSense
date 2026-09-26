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
    super(describe(body));
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
  /** True when a 422 names this request field, e.g. "timezone". */
  concernsField(field: string): boolean {
    const d = this.detail();
    return (
      this.status === 422 &&
      Array.isArray(d) &&
      d.some((e) => Array.isArray(e?.loc) && e.loc.includes(field))
    );
  }
}

/* Every page shows `err.message` as-is, so it has to be a sentence. It used to
 * be JSON.stringify(body), which put {"detail":"Invalid credentials"} -- or a
 * pydantic error list -- in front of the person using the app. FastAPI's
 * detail is a string, an object with a message (the 409s), or pydantic's list
 * of validation errors. */
function describe(body: unknown): string {
  const detail =
    body && typeof body === "object" && "detail" in body
      ? (body as { detail: unknown }).detail
      : body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((e) => {
      const loc: unknown[] = Array.isArray(e?.loc) ? e.loc.slice(1) : [];
      // pydantic prefixes messages raised by our own validators.
      const msg = String(e?.msg ?? "is invalid").replace(/^Value error, /, "");
      return loc.length ? `${loc.join(".")}: ${msg}` : msg;
    });
    if (parts.length) return parts.join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return JSON.stringify(detail);
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

/* Not every 401 means the session is gone. A wrong "current password" when
 * changing it, or when adding a recovery email, is a 401 from a perfectly good
 * session -- and signing out on any 401 turned that typo into a trip back to
 * the login screen. So a 401 elsewhere only prompts a question to /users/me,
 * and only its 401 signs out. Concurrent 401s share the one check. */
let sessionCheck: Promise<unknown> | null = null;

function sessionRejected(path: string): void {
  if (path === "/users/me") {
    onUnauthorized?.();
    return;
  }
  sessionCheck ??= request("GET", "/users/me")
    .catch(() => undefined)
    .finally(() => {
      sessionCheck = null;
    });
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
  // Possibly: the session is gone, expired, or was revoked elsewhere.
  if (res.status === 401) sessionRejected(path);
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
  if (res.status === 401) sessionRejected(path);
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
  /** IANA zone the user's day is counted in; null until a client reports one
   *  (the server then counts in UTC). */
  timezone: string | null;
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
  /** null when the period has no scored days -- never a made-up 0. */
  user_recent_avg_score: number | null;
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

/** One local calendar day of GET /reports/trend. */
export interface TrendPoint {
  /** YYYY-MM-DD in the user's own time zone. */
  date: string;
  /** The day's first evening check-in; null = no check-in (a gap, not a zero). */
  score: number | null;
  /** More than 1 means retakes, which do not count. */
  attempts: number;
  /** Trailing mean and its 95% interval; the interval is null below 3 days. */
  rolling_mean: number | null;
  rolling_ci_low: number | null;
  rolling_ci_high: number | null;
  rolling_scored_days: number;
}

/** The daily series plus the same trajectory the risk report computes, so for
 *  the same window the chart and the report cannot disagree. */
export interface Trend {
  window_days: number;
  timezone: string;
  rolling_days: number;
  points: TrendPoint[];
  n_scored_days: number;
  recent_avg: number | null;
  recent_avg_ci_low: number | null;
  recent_avg_ci_high: number | null;
  baseline_avg: number | null;
  baseline_ci_low: number | null;
  baseline_ci_high: number | null;
  baseline_days: number;
  change_pct: number | null;
  change_ci_low_pct: number | null;
  change_ci_high_pct: number | null;
  elevated_concern: boolean;
  concern_reason: string | null;
  inconclusive: boolean;
  inconclusive_reason: string | null;
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
