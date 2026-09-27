import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { AlertTriangle, ChartLine, CheckCircle2, Info } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { api, type Trend, type TrendPoint } from "@/lib/api";
import { cn } from "@/lib/utils";

/* The biweekly / monthly trend: every local day in the window, the day's score
 * as a dot, the trailing mean as a line, and the 95% interval on that mean as a
 * band -- a single day is one observation and has no interval of its own. The
 * judgement under it is the risk report's own trajectory analysis on the same
 * inputs (backend: GET /reports/trend), so the two cannot disagree. */

const WINDOWS = [14, 30] as const;
type WindowDays = (typeof WINDOWS)[number];

export function TrendReport({ userId }: { userId: number }) {
  const [windowDays, setWindowDays] = useState<WindowDays>(14);
  const [loaded, setLoaded] = useState<Partial<Record<WindowDays, Trend>>>({});
  const [error, setError] = useState<string | null>(null);
  const summaryId = useId();

  // Each window is fetched once; switching back is instant.
  useEffect(() => {
    if (loaded[windowDays]) return;
    let ignore = false;
    api.get<Trend>(`/reports/trend/${userId}?days=${windowDays}`).then(
      (t) => {
        if (!ignore) setLoaded((prev) => ({ ...prev, [windowDays]: t }));
      },
      (e) => {
        if (!ignore) setError(e instanceof Error ? e.message : "Could not load your trend");
      },
    );
    return () => {
      ignore = true;
    };
  }, [userId, windowDays, loaded]);

  // While another window loads, the previous chart stays up, dimmed: no
  // skeleton flash and no layout jump.
  const trend = loaded[windowDays] ?? Object.values(loaded)[0];
  const stale = !loaded[windowDays] && !!trend;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-1.5 text-subhead font-semibold text-ios-pink">
            <ChartLine className="h-4 w-4" strokeWidth={2.5} /> Your trend
          </CardTitle>
          <CardDescription>
            Each dot is one day&apos;s score. The line is your 7-day average and the
            shading its 95% range.
          </CardDescription>
        </div>
        <SegmentedControl
          label="Time range"
          value={windowDays}
          onChange={(w) => {
            setError(null);
            setWindowDays(w);
          }}
          options={WINDOWS.map((w) => ({ value: w, label: `${w} days` }))}
        />
      </CardHeader>
      <CardContent>
        {error && <p className="mb-3 text-subhead text-danger">{error}</p>}
        {!trend ? (
          !error && <div className="h-72 animate-pulse rounded-xl bg-fill-2" />
        ) : (
          <div className={cn("transition-opacity", stale && "opacity-50")} aria-busy={stale}>
            <TrendSummary trend={trend} id={summaryId} />
            <Legend hasBaseline={trend.baseline_avg != null} />
            <TrendChart trend={trend} labelledBy={summaryId} />
            <TrendTable trend={trend} />
            <p className="mt-3 text-footnote text-label-2">
              Days are counted in {trend.timezone.replaceAll("_", " ")}. A day without a
              dot had no evening check-in; it is left as a gap, not counted as zero. If
              the test was taken twice in a day, only the first attempt counts.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------ summary */

function TrendSummary({ trend, id }: { trend: Trend; id: string }) {
  const t = trend;
  return (
    <div className="mb-4 space-y-3">
      <p id={id} className="text-subhead text-label">
        Last {t.window_days} days: you checked in on {t.n_scored_days} of them.{" "}
        {t.recent_avg != null && (
          <>
            Your average was <strong>{pct(t.recent_avg)}</strong>
            {range(t.recent_avg_ci_low, t.recent_avg_ci_high)
              ? ` (95% range ${range(t.recent_avg_ci_low, t.recent_avg_ci_high)}). `
              : " — too few days to give a range yet. "}
          </>
        )}
        {t.baseline_avg != null ? (
          <>
            Your baseline, from your first {t.baseline_days} scored day
            {t.baseline_days === 1 ? "" : "s"}, is <strong>{pct(t.baseline_avg)}</strong>
            {range(t.baseline_ci_low, t.baseline_ci_high)
              ? ` (95% range ${range(t.baseline_ci_low, t.baseline_ci_high)}).`
              : "."}
          </>
        ) : (
          "There is no baseline yet: every scored day so far falls inside this window."
        )}
      </p>
      <TrendStatus trend={t} />
    </div>
  );
}

/* Status wears its icon and a label, never colour alone. "Not enough to say"
 * is its own state -- it must never collapse into the reassuring one. */
function TrendStatus({ trend: t }: { trend: Trend }) {
  if (t.elevated_concern && t.concern_reason) {
    return (
      <StatusLine
        icon={<AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-ios-orange" strokeWidth={2.25} />}
        label="Attention"
        body={t.concern_reason}
        className="bg-ios-orange/12 text-label"
      />
    );
  }
  if (t.inconclusive && t.inconclusive_reason) {
    return (
      <StatusLine
        icon={<Info className="mt-0.5 h-4 w-4 shrink-0 text-ios-blue" strokeWidth={2.25} />}
        label="Not enough to say yet"
        body={t.inconclusive_reason}
        className="bg-ios-blue/10 text-label"
      />
    );
  }
  const neutral = "bg-fill-2 text-label";
  const lo = t.change_ci_low_pct;
  const hi = t.change_ci_high_pct;
  if (t.change_pct == null || lo == null || hi == null) {
    return null;
  }
  const change = `${signed(t.change_pct)} (95% range ${signed(lo)} to ${signed(hi)})`;

  // Same reading as the rest of the app: a change counts as more than
  // day-to-day variation only when its whole interval clears zero. A decline
  // that does, but is smaller than the drop the report warns about, is said
  // plainly -- neither dressed up as a warning nor waved away as noise.
  if (hi < 0) {
    return (
      <StatusLine
        icon={<Info className="mt-0.5 h-4 w-4 shrink-0 text-label-2" strokeWidth={2.25} />}
        label="A small decline"
        body={`Compared with your baseline: ${change}. That is more than day-to-day variation, but smaller than the drop this app treats as a reason for attention. Keep checking in.`}
        className={neutral}
      />
    );
  }
  if (lo > 0) {
    return (
      <StatusLine
        icon={<Info className="mt-0.5 h-4 w-4 shrink-0 text-label-2" strokeWidth={2.25} />}
        label="Above your baseline"
        body={`Compared with your baseline: ${change}.`}
        className={neutral}
      />
    );
  }
  return (
    <StatusLine
      icon={<CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-label-2" strokeWidth={2.25} />}
      label="No change beyond day-to-day variation"
      body={`Compared with your baseline: ${change}.`}
      className={neutral}
    />
  );
}

function StatusLine(props: { icon: ReactNode; label: string; body: string; className: string }) {
  return (
    <div className={cn("flex items-start gap-2 rounded-xl px-4 py-3 text-subhead ", props.className)}>
      {props.icon}
      <p>
        <span className="font-semibold">{props.label}.</span> {props.body}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------- legend */

function Legend({ hasBaseline }: { hasBaseline: boolean }) {
  const key = "flex items-center gap-1.5";
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-footnote text-label-2">
      <li className={key}>
        <svg width="10" height="10" aria-hidden="true">
          <circle cx="5" cy="5" r="4" className="fill-tint" />
        </svg>
        Daily score
      </li>
      <li className={key}>
        <svg width="16" height="10" aria-hidden="true">
          <line x1="1" y1="5" x2="15" y2="5" strokeWidth="2" strokeLinecap="round" className="stroke-tint" />
        </svg>
        7-day average
      </li>
      <li className={key}>
        <svg width="16" height="10" aria-hidden="true">
          <rect width="16" height="10" rx="2" className="fill-tint/15" />
        </svg>
        95% range of the average
      </li>
      {hasBaseline && (
        <li className={key}>
          <svg width="16" height="10" aria-hidden="true">
            <line x1="1" y1="5" x2="15" y2="5" strokeWidth="1.5" className="stroke-ios-gray" />
          </svg>
          Your baseline
        </li>
      )}
    </ul>
  );
}

/* -------------------------------------------------------------- chart */

// Height includes the x-axis band, so the labels are never cut off or
// scrolled inside the card.
const HEIGHT = 224;
const TOP = 14;
const BOTTOM = 28;
const LEFT = 40;
const RIGHT = 16;

/* The y-axis starts at 50%, 25% or 0% -- whichever is the highest floor that
 * still holds every value on the chart. Scores mostly sit between 60% and 90%,
 * so a fixed 0-100% axis pressed them into a thin strip where a real change
 * was hard to see. The floors are fixed steps rather than fitted to the data,
 * so the scale does not jump about from one day to the next, and a few points
 * of change are never stretched across the whole plot. */
function yDomain(trend: Trend): { min: number; ticks: number[] } {
  const values = trend.points.flatMap((p) => [p.score, p.rolling_ci_low]);
  const lowest = Math.min(1, ...values.filter((v): v is number => v != null), trend.baseline_avg ?? 1);
  const min = lowest >= 0.55 ? 0.5 : lowest >= 0.3 ? 0.25 : 0;
  const step = min === 0.5 ? 0.1 : 0.25;
  const ticks: number[] = [];
  for (let v = min; v <= 1.0001; v += step) ticks.push(Math.round(v * 100) / 100);
  return { min, ticks };
}

function TrendChart({ trend, labelledBy }: { trend: Trend; labelledBy: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  // Drawn at the real pixel width rather than scaled from a fixed viewBox, so
  // the 11px axis labels stay 11px on a phone instead of shrinking with it.
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const points = trend.points;
  const n = points.length;
  const plotW = Math.max(0, width - LEFT - RIGHT);
  const plotH = HEIGHT - TOP - BOTTOM;
  const { min: yMin, ticks: yTicks } = yDomain(trend);
  const x = (i: number) => LEFT + (n <= 1 ? plotW / 2 : (i * plotW) / (n - 1));
  const y = (v: number) => TOP + ((1 - Math.min(1, Math.max(yMin, v))) / (1 - yMin)) * plotH;

  const withBand = runs(points, (p) => p.rolling_ci_low != null && p.rolling_ci_high != null);
  const xTicks = dayTicks(n, plotW);
  const baseline = trend.baseline_avg;

  function indexAt(clientX: number): number {
    const rect = wrapRef.current!.getBoundingClientRect();
    const i = Math.round(((clientX - rect.left - LEFT) / Math.max(plotW, 1)) * (n - 1));
    return Math.min(n - 1, Math.max(0, i));
  }

  function onKeyDown(e: KeyboardEvent) {
    const last = n - 1;
    const moves: Record<string, (i: number) => number> = {
      ArrowLeft: (i) => Math.max(0, i - 1),
      ArrowRight: (i) => Math.min(last, i + 1),
      Home: () => 0,
      End: () => last,
    };
    if (e.key === "Escape") return setActive(null);
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    setActive((i) => move(i ?? last));
  }

  const p = active != null ? points[active] : null;

  return (
    <div
      ref={wrapRef}
      className="relative w-full select-none rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-tint/50"
      style={{ height: HEIGHT }}
      tabIndex={0}
      aria-label="Chart of your daily scores. Use the left and right arrow keys to read each day."
      onKeyDown={onKeyDown}
      onFocus={() => setActive((i) => i ?? n - 1)}
      onBlur={() => setActive(null)}
      onPointerMove={(e: PointerEvent) => n > 0 && setActive(indexAt(e.clientX))}
      onPointerLeave={() => setActive(null)}
    >
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-labelledby={labelledBy} className="block">
          {/* Recessive frame: solid hairlines, one step off the surface. */}
          {yTicks.map((v) => (
            <g key={v}>
              <line
                x1={LEFT}
                x2={LEFT + plotW}
                y1={y(v)}
                y2={y(v)}
                strokeWidth={1}
                shapeRendering="crispEdges"
                className="stroke-separator"
              />
              <text
                x={LEFT - 8}
                y={y(v)}
                dy="0.32em"
                textAnchor="end"
                fontSize={11}
                className="fill-label-2 tabular-nums"
              >
                {Math.round(v * 100)}%
              </text>
            </g>
          ))}
          {xTicks.map((i) => (
            <text
              key={i}
              x={x(i)}
              y={HEIGHT - 8}
              textAnchor={i === n - 1 ? "end" : "middle"}
              fontSize={11}
              className="fill-label-2"
            >
              {i === n - 1 ? "Today" : shortDate(points[i].date)}
            </text>
          ))}

          {/* 95% band on the trailing mean: a wash, drawn only where there are
              enough days for an interval. A lone day's interval is a bar. */}
          {withBand.map((run) =>
            run.length === 1 ? (
              <line
                key={run[0]}
                x1={x(run[0])}
                x2={x(run[0])}
                y1={y(points[run[0]].rolling_ci_high!)}
                y2={y(points[run[0]].rolling_ci_low!)}
                strokeWidth={6}
                strokeLinecap="round"
                className="stroke-tint/15"
              />
            ) : (
              <path key={run[0]} d={bandPath(run, points, x, y)} className="fill-tint/15" />
            ),
          )}

          {baseline != null && (
            <g>
              <line
                x1={LEFT}
                x2={LEFT + plotW}
                y1={y(baseline)}
                y2={y(baseline)}
                strokeWidth={1.5}
                className="stroke-ios-gray"
              />
              <text
                x={LEFT + plotW}
                y={baseline > 0.9 ? y(baseline) + 15 : y(baseline) - 6}
                textAnchor="end"
                fontSize={11}
                paintOrder="stroke"
                strokeWidth={3}
                className="fill-label-2 stroke-surface"
              >
                Baseline {pct(baseline)}
              </text>
            </g>
          )}

          {/* The mean, only where its interval exists: a number never goes
              out without its range. */}
          {withBand
            .filter((run) => run.length > 1)
            .map((run) => (
              <path
                key={run[0]}
                d={run.map((i, k) => `${k ? "L" : "M"}${x(i)},${y(points[i].rolling_mean!)}`).join("")}
                fill="none"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="stroke-tint"
              />
            ))}

          {active != null && (
            <line
              x1={x(active)}
              x2={x(active)}
              y1={TOP}
              y2={TOP + plotH}
              strokeWidth={1}
              shapeRendering="crispEdges"
              className="stroke-label-3"
            />
          )}

          {/* Days with a check-in. A 2px ring in the surface colour keeps each
              dot legible where it crosses the line. */}
          {points.map((pt, i) =>
            pt.score == null ? null : (
              <circle
                key={pt.date}
                cx={x(i)}
                cy={y(pt.score)}
                r={i === active ? 6 : 4}
                strokeWidth={2}
                className="fill-tint stroke-surface"
              />
            ),
          )}

          {trend.n_scored_days === 0 && (
            <text
              x={LEFT + plotW / 2}
              y={TOP + plotH / 2}
              textAnchor="middle"
              fontSize={13}
              className="fill-label-2"
            >
              No evening check-ins in these {n} days
            </text>
          )}
        </svg>
      )}

      {p && active != null && (
        <div
          aria-live="polite"
          className="pointer-events-none absolute top-1 z-10 w-52 -translate-x-1/2 rounded-xl bg-bar px-3 py-2 text-footnote shadow-[0_8px_24px_rgb(0_0_0/0.14)] ring-[0.5px] ring-separator backdrop-blur-xl backdrop-saturate-[1.8]"
          style={{ left: Math.min(Math.max(x(active), 108), Math.max(width - 108, 108)) }}
        >
          <p className="mb-1 font-medium text-label-2">{longDate(p.date)}</p>
          <p className="flex items-baseline gap-2">
            <svg width="10" height="10" aria-hidden="true" className="shrink-0 self-center">
              <circle cx="5" cy="5" r="4" className="fill-tint" />
            </svg>
            {p.score != null ? (
              <>
                <strong className="text-subhead text-label">{pct(p.score)}</strong>
                <span className="text-label-2">
                  daily score{p.attempts > 1 ? ` (first of ${p.attempts} attempts)` : ""}
                </span>
              </>
            ) : (
              <span className="text-label-2">No check-in this day</span>
            )}
          </p>
          <p className="mt-1 flex items-baseline gap-2">
            <svg width="12" height="10" aria-hidden="true" className="shrink-0 self-center">
              <line x1="1" y1="5" x2="11" y2="5" strokeWidth="2" strokeLinecap="round" className="stroke-tint" />
            </svg>
            {range(p.rolling_ci_low, p.rolling_ci_high) ? (
              <>
                <strong className="text-subhead text-label">{pct(p.rolling_mean!)}</strong>
                <span className="text-label-2">
                  7-day average, range {range(p.rolling_ci_low, p.rolling_ci_high)}
                </span>
              </>
            ) : (
              <span className="text-label-2">
                7-day average: too few days for a range
              </span>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- table */

/* The chart's twin: every value is readable here without hovering. */
function TrendTable({ trend }: { trend: Trend }) {
  return (
    <details className="mt-4">
      <summary className="cursor-pointer text-subhead font-medium text-link hover:underline">
        Show the numbers
      </summary>
      <div className="mt-2 max-h-72 overflow-auto rounded-xl ring-[0.5px] ring-separator">
        <table className="w-full text-left text-footnote tabular-nums">
          <caption className="sr-only">
            Daily scores and 7-day averages for the last {trend.window_days} days, newest first
          </caption>
          <thead className="sticky top-0 bg-surface text-label-2">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Day</th>
              <th scope="col" className="px-3 py-2 font-medium">Score</th>
              <th scope="col" className="px-3 py-2 font-medium">7-day average</th>
              <th scope="col" className="px-3 py-2 font-medium">95% range</th>
            </tr>
          </thead>
          <tbody className="text-label">
            {[...trend.points].reverse().map((p) => (
              <tr key={p.date} className="border-t-[0.5px] border-separator">
                <th scope="row" className="px-3 py-1.5 font-normal">{longDate(p.date)}</th>
                <td className="px-3 py-1.5">
                  {p.score != null ? pct(p.score) : <span className="text-label-3">no check-in</span>}
                </td>
                <td className="px-3 py-1.5">
                  {range(p.rolling_ci_low, p.rolling_ci_high) ? pct(p.rolling_mean!) : "—"}
                </td>
                <td className="px-3 py-1.5">{range(p.rolling_ci_low, p.rolling_ci_high) ?? "too few days"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/* ------------------------------------------------------------ helpers */

/** Runs of consecutive indices where `has` holds; a gap ends a run. */
function runs(points: TrendPoint[], has: (p: TrendPoint) => boolean): number[][] {
  const out: number[][] = [];
  let current: number[] = [];
  points.forEach((p, i) => {
    if (has(p)) {
      current.push(i);
    } else if (current.length) {
      out.push(current);
      current = [];
    }
  });
  if (current.length) out.push(current);
  return out;
}

function bandPath(
  run: number[],
  points: TrendPoint[],
  x: (i: number) => number,
  y: (v: number) => number,
): string {
  const upper = run.map((i, k) => `${k ? "L" : "M"}${x(i)},${y(points[i].rolling_ci_high!)}`);
  const lower = [...run].reverse().map((i) => `L${x(i)},${y(points[i].rolling_ci_low!)}`);
  return `${upper.join("")}${lower.join("")}Z`;
}

/** Tick positions counted back from today, about one per 72px. */
function dayTicks(n: number, plotW: number): number[] {
  if (n === 0) return [];
  const maxTicks = Math.max(2, Math.floor(plotW / 72));
  const step = Math.max(1, Math.ceil((n - 1) / (maxTicks - 1)));
  const ticks: number[] = [];
  for (let i = n - 1; i >= 0; i -= step) ticks.unshift(i);
  // Drop a first tick crowded against its neighbour.
  if (ticks.length > 1 && ticks[1] - ticks[0] < step / 2) ticks.shift();
  return ticks;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function signed(v: number): string {
  const r = Math.round(v);
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r)}%`;
}

function range(lo: number | null, hi: number | null): string | null {
  return lo != null && hi != null ? `${Math.round(lo * 100)}–${Math.round(hi * 100)}%` : null;
}

/* Dates are the user's local calendar days, sent as YYYY-MM-DD. Formatted in
 * UTC so the browser's own zone cannot shift one to the day before. */
function asDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

const SHORT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
const LONG = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function shortDate(iso: string): string {
  return SHORT.format(asDate(iso));
}

function longDate(iso: string): string {
  return LONG.format(asDate(iso));
}
