import { useEffect, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Activity, Info, TriangleAlert, Users, UserRound } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card } from "@/components/ui/Card";
import { GroupedList, ListRow } from "@/components/ui/List";
import { Disclaimer } from "@/components/Disclaimer";
import { TrendReport } from "@/components/TrendReport";
import { api, type RiskComparison } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function ReportPage() {
  const { user } = useAuth();
  const [data, setData] = useState<RiskComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api
      .get<RiskComparison>(`/reports/risk-comparison/${user.id}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [user]);

  if (!user) return null;

  return (
    <Shell
      title="Report"
      subtitle="Your scores, next to research benchmarks for your age, gender and ethnicity."
    >
      {error && <p className="mb-4 px-1 text-subhead text-danger">{error}</p>}
      {!data ? (
        <Skeleton />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric
              icon={<Activity className="h-4 w-4" strokeWidth={2.5} />}
              tone="text-ios-pink"
              label="Recent average"
              value={
                data.user_recent_avg_score == null
                  ? "—"
                  : `${Math.round(data.user_recent_avg_score * 100)}%`
              }
              hint={
                data.user_recent_avg_score == null
                  ? "No scored days in the last 14 yet"
                  : data.user_recent_avg_ci_low != null && data.user_recent_avg_ci_high != null
                    ? `95% range ${Math.round(data.user_recent_avg_ci_low * 100)}–${Math.round(
                        data.user_recent_avg_ci_high * 100,
                      )}% · ${data.n_scored_days} scored days`
                    : `${data.n_scored_days} scored day${
                        data.n_scored_days === 1 ? "" : "s"
                      } — too few to give a range yet`
              }
            />
            <Metric
              icon={<Users className="h-4 w-4" strokeWidth={2.5} />}
              tone="text-ios-indigo"
              label="Peer ADRD prevalence"
              value={`${data.peer_expected_prevalence_pct.toFixed(1)}%`}
              hint="Matched by age, gender and race"
            />
            <Metric
              icon={<UserRound className="h-4 w-4" strokeWidth={2.5} />}
              tone="text-ios-teal"
              label="Peer subjective decline"
              value={`${data.scd_peer_prevalence_pct.toFixed(1)}%`}
              hint="Self-reported, CDC BRFSS 2023"
            />
          </div>

          {data.elevated_concern && data.concern_reason && (
            <Callout
              icon={<TriangleAlert className="h-5 w-5" strokeWidth={2.25} />}
              iconTone="bg-ios-orange"
              title="Attention"
              body={data.concern_reason}
            />
          )}

          {/* Not the same as "you're fine". The backend reports this when the
              data cannot yet separate a real decline from normal variation;
              showing nothing here would read as an all-clear. */}
          {data.inconclusive && data.inconclusive_reason && (
            <Callout
              icon={<Info className="h-5 w-5" strokeWidth={2.25} />}
              iconTone="bg-ios-blue"
              title="Not enough to say yet"
              body={data.inconclusive_reason}
              detail={
                data.trajectory_change_pct != null &&
                data.trajectory_change_ci_low_pct != null &&
                data.trajectory_change_ci_high_pct != null
                  ? `Change vs. your baseline: ${signed(data.trajectory_change_pct)} (95% range ${signed(
                      data.trajectory_change_ci_low_pct,
                    )} to ${signed(data.trajectory_change_ci_high_pct)})`
                  : undefined
              }
            />
          )}

          <TrendReport userId={user.id} />

          <GroupedList header="Suggestions" footer="From the 14 Lancet 2024 modifiable risk factors.">
            {data.suggestions.map((s, i) => {
              const colon = s.indexOf(":");
              return colon > 0 ? (
                <ListRow key={i} title={s.slice(0, colon)} subtitle={s.slice(colon + 1).trim()} />
              ) : (
                <ListRow key={i} title={s} />
              );
            })}
          </GroupedList>

          <section>
            <h2 className="px-4 pb-1.5 text-footnote uppercase text-label-2">Sources</h2>
            <ul className="space-y-1 px-4">
              {data.citations.map((c, i) => (
                <li key={i} className="text-footnote text-label-2">
                  {c}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}

      <Disclaimer />
    </Shell>
  );
}

/* A Health-style summary card: a coloured label, then the number in rounded
 * figures, then what it means. */
function Metric(props: { icon: ReactNode; tone: string; label: string; value: string; hint: string }) {
  return (
    <Card className="px-4 py-3.5">
      <p className={`flex items-center gap-1.5 text-subhead font-semibold ${props.tone}`}>
        {props.icon}
        {props.label}
      </p>
      <p className="mt-1.5 font-rounded text-large-title font-bold tracking-tight text-label tabular-nums">
        {props.value}
      </p>
      <p className="mt-0.5 text-footnote text-label-2">{props.hint}</p>
    </Card>
  );
}

function Callout(props: { icon: ReactNode; iconTone: string; title: string; body: string; detail?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <Card className="flex items-start gap-3 px-4 py-3.5">
        <span
          aria-hidden="true"
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ${props.iconTone}`}
        >
          {props.icon}
        </span>
        <div>
          <p className="text-body font-semibold text-label">{props.title}</p>
          <p className="mt-0.5 text-subhead text-label-2">{props.body}</p>
          {props.detail && <p className="mt-1.5 text-footnote text-label-2 tabular-nums">{props.detail}</p>}
        </div>
      </Card>
    </motion.div>
  );
}

function signed(v: number): string {
  const r = Math.round(v);
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r)}%`;
}

function Skeleton() {
  return (
    <div className="space-y-3" aria-busy="true">
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-fill-2" />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-2xl bg-fill-2" />
    </div>
  );
}
