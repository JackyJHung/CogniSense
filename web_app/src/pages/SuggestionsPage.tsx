import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type DailySuggestions } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function SuggestionsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState<DailySuggestions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api
      .get<DailySuggestions>(`/reports/daily-suggestions/${user.id}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [user]);

  if (!user) return null;

  return (
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-brand-500" />
            <CardTitle>Daily suggestions</CardTitle>
          </div>
          <CardDescription>
            Tailored to your life stage from the Lancet 2024 modifiable-risk-factor framework.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
          {!data ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-xl bg-white/40 dark:bg-white/5" />
              ))}
            </div>
          ) : (
            <ul className="space-y-3">
              {data.suggestions.map((s, i) => {
                const colon = s.indexOf(":");
                const head = colon > 0 ? s.slice(0, colon) : null;
                const body = colon > 0 ? s.slice(colon + 1).trim() : s;
                return (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.06 }}
                    className="rounded-xl bg-white/40 dark:bg-white/[0.03] px-4 py-3 ring-1 ring-slate-200/40 dark:ring-white/5"
                  >
                    {head && (
                      <p className="text-xs font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">
                        {head}
                      </p>
                    )}
                    <p className="mt-0.5 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                      {body}
                    </p>
                  </motion.li>
                );
              })}
            </ul>
          )}
          {data && (
            <p className="mt-4 text-xs italic text-slate-500 dark:text-slate-400">
              {data.lancet_risk_factor_source}
            </p>
          )}
        </CardContent>
      </Card>

      <Disclaimer />
    </Shell>
  );
}
