import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, ImageIcon } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api, ApiError, type EveningCheckin } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type ConflictDetail = {
  code?: string;
  message?: string;
  existing?: EveningCheckin;
};

export function EveningPage() {
  const navigate = useNavigate();
  const { user, morning } = useAuth();
  // Response latency is measured from here. Stamped in an effect rather than
  // during render: render must stay pure (React may run it more than once),
  // and the clock should start once the cues are actually on screen.
  const startRef = useRef<number>(0);
  useEffect(() => {
    startRef.current = Date.now();
  }, []);
  const [recalled, setRecalled] = useState("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<EveningCheckin | null>(null);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!user) return null;

  if (!morning) {
    return (
      <Shell>
        <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Button>
        <Card>
          <CardHeader>
            <CardTitle>No morning check-in yet</CardTitle>
            <CardDescription>
              You need to complete the morning check-in first so we have associations to test.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/morning">
              <Button>Go to morning check-in</Button>
            </Link>
          </CardContent>
        </Card>
        <Disclaimer />
      </Shell>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const now = Date.now();
      const responses = morning.presented_associations.map((a) => ({
        association_id: a.id,
        user_answer: answers[a.id] ?? "",
        response_latency_ms: now - startRef.current,
      }));
      const ev = await api.post<EveningCheckin>("/checkins/evening", {
        user_id: user.id,
        morning_checkin_id: morning.id,
        recalled_activities: recalled.trim(),
        association_responses: responses,
      });
      setResult(ev);
    } catch (err) {
      // One test per morning: a retake has already seen the answers. The server
      // sends back the first attempt, which is the day's result.
      const detail =
        err instanceof ApiError && err.status === 409 ? (err.detail() as ConflictDetail | null) : null;
      if (detail?.existing) {
        setResult(detail.existing);
        setAlreadySubmitted(true);
      } else {
        setError(err instanceof Error ? err.message : "Could not save");
      }
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    const score = result.daily_cognitive_score ?? 0;
    return (
      <Shell>
        <header className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Daily results
          </h1>
          {alreadySubmitted && (
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
              You had already taken this evening's test. This is the result that counts; the
              answers you just entered were not scored.
            </p>
          )}
        </header>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardContent className="pt-6">
              <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Daily cognitive score
              </p>
              <div className="mt-1 flex items-baseline gap-0.5">
                <motion.span
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5 }}
                  className="text-5xl font-semibold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums"
                >
                  {Math.round(score * 100)}
                </motion.span>
                <span className="text-2xl font-semibold text-slate-400 dark:text-slate-500">%</span>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200/60 dark:bg-white/10">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                  className="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600"
                />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Stat label="Image-association accuracy" value={`${Math.round(result.association_accuracy * 100)}%`} />
                <Stat label="Activity recall" value={`${Math.round((result.activity_recall_accuracy ?? 0) * 100)}%`} />
                <Stat label="Avg response latency" value={`${result.avg_response_latency_ms ?? 0} ms`} />
                <Stat
                  label="Speech biomarker"
                  value={
                    result.speech_biomarker_score == null
                      ? "Not recorded"
                      : result.speech_biomarker_score.toFixed(2)
                  }
                />
              </dl>
            </CardContent>
          </Card>
        </div>
        <div className="mt-6 flex gap-3">
          <Link to="/report"><Button>View risk report</Button></Link>
          <Button variant="secondary" onClick={() => navigate("/dashboard")}>Back to dashboard</Button>
        </div>
        <Disclaimer />
      </Shell>
    );
  }

  return (
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>
      <form onSubmit={submit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>What do you remember doing today?</CardTitle>
            <CardDescription>Free-text recall — list everything you can think of.</CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea value={recalled} onChange={(e) => setRecalled(e.target.value)} required rows={5} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Image-association test</CardTitle>
            <CardDescription>For each cue word, type the object you were shown this morning.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2">
              {morning.presented_associations.map((a, i) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.06 }}
                  className="rounded-xl border border-slate-200/60 dark:border-white/10 bg-white/50 dark:bg-white/5 p-4"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-700/30">
                      <ImageIcon className="h-5 w-5 text-brand-600 dark:text-brand-300" />
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Cue</p>
                      <p className="font-semibold text-slate-900 dark:text-slate-100">"{a.cue_word}"</p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-col gap-1.5">
                    <Label htmlFor={`a-${a.id}`}>Object</Label>
                    <Input
                      id={`a-${a.id}`}
                      value={answers[a.id] ?? ""}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [a.id]: e.target.value }))}
                      placeholder="your answer"
                      required
                    />
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>

        {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <Button type="submit" loading={loading} size="lg">
          Submit evening check-in
        </Button>
      </form>
      <Disclaimer />
    </Shell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-200/40 dark:border-white/5 pb-2 last:border-0 last:pb-0">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</dd>
    </div>
  );
}
