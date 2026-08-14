import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, ImageIcon, Lock } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Disclaimer } from "@/components/Disclaimer";
import { api, ApiError, type MorningCheckin } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type ConflictDetail = {
  code?: string;
  message?: string;
  existing?: MorningCheckin;
};

export function MorningPage() {
  const navigate = useNavigate();
  const { user, setMorning } = useAuth();
  const [plans, setPlans] = useState("");
  const [result, setResult] = useState<MorningCheckin | null>(null);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);
  const [checkingExisting, setCheckingExisting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // On mount: check if there's already a morning check-in for today.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const existing = await api.get<MorningCheckin>(`/checkins/morning/today/${user.id}`);
        if (cancelled) return;
        setResult(existing);
        setAlreadySubmitted(true);
        setMorning(existing);
      } catch (err) {
        // 404 = no morning yet today, expected — anything else is a real error
        if (!(err instanceof ApiError && err.status === 404) && !cancelled) {
          setError(err instanceof Error ? err.message : "Could not load today's check-in");
        }
      } finally {
        if (!cancelled) setCheckingExisting(false);
      }
    })();
    return () => { cancelled = true; };
  }, [user, setMorning]);

  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const morning = await api.post<MorningCheckin>("/checkins/morning", {
        user_id: user.id,
        planned_activities: plans.trim(),
      });
      setMorning(morning);
      setResult(morning);
    } catch (err) {
      // Handle the "already submitted today" race condition
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail() as ConflictDetail | null;
        if (detail?.existing) {
          setMorning(detail.existing);
          setResult(detail.existing);
          setAlreadySubmitted(true);
        } else {
          setError(detail?.message ?? "Morning check-in already submitted today.");
        }
      } else {
        setError(err instanceof Error ? err.message : "Could not save");
      }
    } finally {
      setLoading(false);
    }
  };

  if (checkingExisting) {
    return (
      <Shell>
        <div className="h-48 animate-pulse rounded-2xl bg-white/40 dark:bg-white/5" />
      </Shell>
    );
  }

  return (
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>

      {!result ? (
        <Card>
          <CardHeader>
            <CardTitle>Morning check-in</CardTitle>
            <CardDescription>
              List what you plan to do today, one per line. After you submit, we'll show you
              five image associations to remember — you'll be tested on them tonight.
              <br />
              <span className="mt-1 inline-block text-xs text-slate-500 dark:text-slate-400">
                You can only submit once per day. Make sure your list is complete before you submit.
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="flex flex-col gap-4">
              <Textarea
                placeholder={"e.g.\nMorning walk in the park\nGrocery shopping\nCall Mom\nFinish chapter 3"}
                rows={7}
                value={plans}
                onChange={(e) => setPlans(e.target.value)}
                required
                minLength={3}
              />
              {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
              <Button type="submit" loading={loading} size="lg">
                Submit & show associations
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <>
          <header className="mb-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                  {alreadySubmitted ? "Today's morning check-in" : "Remember these"}
                </h1>
                <p className="mt-2 text-slate-600 dark:text-slate-400">
                  Tonight we'll show you each cue word and ask you to name the object.
                </p>
              </div>
              {alreadySubmitted && (
                <div className="flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  <Lock className="h-3.5 w-3.5" />
                  Locked for today
                </div>
              )}
            </div>
            {alreadySubmitted && (
              <div className="mt-4 rounded-xl border border-slate-200/60 dark:border-white/10 bg-white/50 dark:bg-white/[0.03] p-4 text-sm">
                <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Your plans for today
                </p>
                <p className="mt-1 whitespace-pre-line text-slate-800 dark:text-slate-200">
                  {result.planned_activities}
                </p>
                <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                  Submitted {new Date(result.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.
                  You can come back to this page to review the associations at any time today,
                  but you can't submit again until tomorrow.
                </p>
              </div>
            )}
          </header>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {result.presented_associations.map((a, i) => (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.35, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              >
                <Card className="overflow-hidden">
                  <div className="flex h-40 items-center justify-center bg-gradient-to-br from-brand-100 to-brand-300/40 dark:from-brand-700/30 dark:to-brand-500/20">
                    <ImageIcon className="h-12 w-12 text-brand-600/50 dark:text-brand-300/60" />
                  </div>
                  <CardContent className="pt-5">
                    <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Cue
                    </p>
                    <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                      "{a.cue_word}"
                    </p>
                    <p className="mt-2 text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Object
                    </p>
                    <p className="text-base font-medium text-slate-800 dark:text-slate-200">
                      {a.object_name}
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
          <Button onClick={() => navigate("/dashboard")} className="mt-8" size="lg">
            Done — back to dashboard
          </Button>
        </>
      )}

      <Disclaimer />
    </Shell>
  );
}
