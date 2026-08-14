import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, AlertTriangle, BookOpen, Info } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type RiskComparison } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function ReportPage() {
  const navigate = useNavigate();
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
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Risk report
        </h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Your scores compared to age, gender, and ethnicity-matched research benchmarks.
        </p>
      </header>

      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      {!data ? (
        <Skeleton />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Metric
              label="Your recent average score"
              value={`${Math.round(data.user_recent_avg_score * 100)}%`}
              hint={
                data.user_recent_avg_ci_low != null && data.user_recent_avg_ci_high != null
                  ? `95% range ${Math.round(data.user_recent_avg_ci_low * 100)}–${Math.round(
                      data.user_recent_avg_ci_high * 100,
                    )}% · ${data.n_scored_days} scored days`
                  : `${data.n_scored_days} scored day${
                      data.n_scored_days === 1 ? "" : "s"
                    } — too few to give a range yet`
              }
            />
            <Metric
              label="Peer ADRD prevalence"
              value={`${data.peer_expected_prevalence_pct.toFixed(1)}%`}
              hint="age + gender + race-matched"
            />
            <Metric
              label="Peer subjective decline rate"
              value={`${data.scd_peer_prevalence_pct.toFixed(1)}%`}
              hint="self-reported, CDC BRFSS 2023"
            />
          </div>

          {data.elevated_concern && data.concern_reason && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <Card className="border-amber-500/40 bg-amber-50/70 dark:bg-amber-500/10">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/20 text-amber-700 dark:text-amber-300">
                      <AlertTriangle className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold text-amber-900 dark:text-amber-200">
                        Attention
                      </p>
                      <p className="mt-1 text-sm leading-relaxed text-amber-900/80 dark:text-amber-100/80">
                        {data.concern_reason}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Not the same as "you're fine". The backend reports this when the
              data cannot yet separate a real decline from normal variation;
              showing nothing here would read as an all-clear. */}
          {data.inconclusive && data.inconclusive_reason && (
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <Card className="border-sky-500/40 bg-sky-50/70 dark:bg-sky-500/10">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-500/20 text-sky-700 dark:text-sky-300">
                      <Info className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-semibold text-sky-900 dark:text-sky-200">
                        Not enough to say yet
                      </p>
                      <p className="mt-1 text-sm leading-relaxed text-sky-900/80 dark:text-sky-100/80">
                        {data.inconclusive_reason}
                      </p>
                      {data.trajectory_change_pct != null &&
                        data.trajectory_change_ci_low_pct != null &&
                        data.trajectory_change_ci_high_pct != null && (
                          <p className="mt-2 text-xs text-sky-900/60 dark:text-sky-100/60">
                            Change vs. your baseline:{" "}
                            {data.trajectory_change_pct > 0 ? "+" : ""}
                            {data.trajectory_change_pct.toFixed(0)}% (95% range{" "}
                            {data.trajectory_change_ci_low_pct > 0 ? "+" : ""}
                            {data.trajectory_change_ci_low_pct.toFixed(0)}% to{" "}
                            {data.trajectory_change_ci_high_pct > 0 ? "+" : ""}
                            {data.trajectory_change_ci_high_pct.toFixed(0)}%)
                          </p>
                        )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Suggestions</CardTitle>
              <CardDescription>From the 14 Lancet 2024 modifiable risk factors.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {data.suggestions.map((s, i) => (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.05 }}
                    className="flex items-start gap-3 rounded-xl bg-white/40 dark:bg-white/[0.03] px-4 py-3 ring-1 ring-slate-200/40 dark:ring-white/5"
                  >
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                    <span className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{s}</span>
                  </motion.li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center gap-2">
              <BookOpen className="h-4 w-4 text-slate-500" />
              <CardTitle className="text-base">Sources</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1.5">
                {data.citations.map((c, i) => (
                  <li key={i} className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    {c}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}

      <Disclaimer />
    </Shell>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          {value}
        </p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>
      </CardContent>
    </Card>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/40 dark:bg-white/5" />
        ))}
      </div>
      <div className="h-40 animate-pulse rounded-2xl bg-white/40 dark:bg-white/5" />
    </div>
  );
}
