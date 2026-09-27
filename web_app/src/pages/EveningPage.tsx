import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Moon } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { GroupedList, ListRow } from "@/components/ui/List";
import { Disclaimer } from "@/components/Disclaimer";
import { api, ApiError, type EveningCheckin } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTodaysMorning } from "@/lib/useTodaysMorning";

const TODAY = { to: "/dashboard", label: "Today" };

type ConflictDetail = {
  code?: string;
  message?: string;
  existing?: EveningCheckin;
};

export function EveningPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const today = useTodaysMorning(user?.id);
  const morning = today.morning;
  // Response latency is measured from here. Stamped in an effect rather than
  // during render: render must stay pure (React may run it more than once),
  // and the clock should start once the cues are actually on screen -- which
  // is when today's morning check-in has arrived from the server.
  const startRef = useRef<number>(0);
  useEffect(() => {
    if (morning) startRef.current = Date.now();
  }, [morning]);
  const [recalled, setRecalled] = useState("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<EveningCheckin | null>(null);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!user) return null;

  if (today.loading) {
    return (
      <Shell title="Evening check-in" back={TODAY}>
        <div className="h-48 animate-pulse rounded-2xl bg-fill-2" />
      </Shell>
    );
  }

  if (!morning) {
    return (
      <Shell title="Evening check-in" back={TODAY}>
        <Card className="flex flex-col items-center px-6 py-10 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-ios-indigo text-white">
            <Moon aria-hidden="true" className="h-7 w-7" strokeWidth={2.25} />
          </span>
          <p className="mt-4 text-title3 font-semibold text-label">
            {today.error ? "Couldn't load today's check-in" : "No morning check-in yet"}
          </p>
          <p className="mt-1 max-w-sm text-subhead text-label-2">
            {today.error ??
              "You need to complete the morning check-in first so we have associations to test."}
          </p>
          <div className="mt-6">
            {today.error ? (
              <Button onClick={() => window.location.reload()}>Try Again</Button>
            ) : (
              <Button onClick={() => navigate("/morning")}>Go to Morning Check-in</Button>
            )}
          </div>
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
      <Shell
        title="Daily results"
        back={TODAY}
        subtitle={
          alreadySubmitted
            ? "You had already taken this evening's test. This is the result that counts; the answers you just entered were not scored."
            : undefined
        }
      >
        <Card className="px-5 py-4">
          <p className="text-subhead font-semibold text-ios-indigo">Daily cognitive score</p>
          <p className="mt-1 flex items-baseline font-rounded font-bold tracking-tight text-label tabular-nums">
            <motion.span
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="text-[3.5rem] leading-none"
            >
              {Math.round(score * 100)}
            </motion.span>
            <span className="ml-0.5 text-title2 text-label-2">%</span>
          </p>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-fill">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="h-full rounded-full bg-ios-indigo"
            />
          </div>
          <p className="mt-3 text-footnote text-label-2">
            One day is one data point. Trends need many days; see the report.
          </p>
        </Card>

        <GroupedList header="Details" className="mt-8">
          <ListRow title="Image-association accuracy" value={`${Math.round(result.association_accuracy * 100)}%`} />
          <ListRow title="Activity recall" value={`${Math.round((result.activity_recall_accuracy ?? 0) * 100)}%`} />
          <ListRow title="Average response time" value={`${result.avg_response_latency_ms ?? 0} ms`} />
          <ListRow
            title="Speech biomarker"
            value={result.speech_biomarker_score == null ? "Not recorded" : result.speech_biomarker_score.toFixed(2)}
          />
        </GroupedList>

        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={() => navigate("/report")}>View Report</Button>
          <Button variant="secondary" onClick={() => navigate("/dashboard")}>
            Done
          </Button>
        </div>
        <Disclaimer />
      </Shell>
    );
  }

  return (
    <Shell title="Evening check-in" back={TODAY}>
      <form onSubmit={submit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>What do you remember doing today?</CardTitle>
            <CardDescription>Free-text recall: list everything you can think of.</CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              aria-label="What you remember doing today"
              value={recalled}
              onChange={(e) => setRecalled(e.target.value)}
              required
              rows={5}
            />
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle>Image-association test</CardTitle>
            <CardDescription>For each cue word, type the object you were shown this morning.</CardDescription>
          </CardHeader>
          <ul>
            {morning.presented_associations.map((a, i) => (
              <motion.li
                key={a.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25, delay: i * 0.05 }}
                className="flex items-center gap-4 border-t-[0.5px] border-separator px-5 py-2.5"
              >
                <div className="w-28 shrink-0 sm:w-40">
                  <p className="text-caption font-semibold uppercase text-label-2">Cue</p>
                  <p className="truncate text-body text-label">&ldquo;{a.cue_word}&rdquo;</p>
                </div>
                <Label htmlFor={`a-${a.id}`} className="sr-only">
                  Object for {a.cue_word}
                </Label>
                <Input
                  id={`a-${a.id}`}
                  value={answers[a.id] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [a.id]: e.target.value }))}
                  placeholder="Object"
                  autoCapitalize="none"
                  autoComplete="off"
                  required
                />
              </motion.li>
            ))}
          </ul>
        </Card>

        {error && <p className="px-1 text-subhead text-danger">{error}</p>}
        <Button type="submit" loading={loading} size="lg" className="w-full sm:w-auto">
          Submit
        </Button>
      </form>
      <Disclaimer />
    </Shell>
  );
}
