import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Info } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTodaysMorning } from "@/lib/useTodaysMorning";

export function MiddayPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  // Links the entry to today's morning when there is one; the link is optional.
  const { morning } = useTodaysMorning(user?.id);
  // Latency clock. Stamped after mount, not during render, which must stay
  // pure; addAnother() restarts it for each further entry.
  const startRef = useRef<number>(0);
  useEffect(() => {
    startRef.current = Date.now();
  }, []);
  const [done, setDone] = useState("");
  const [plan, setPlan] = useState("");
  const [success, setSuccess] = useState(false);
  const [submittedCount, setSubmittedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post("/checkins/midday", {
        user_id: user.id,
        morning_checkin_id: morning?.id ?? null,
        what_user_has_done: done.trim(),
        planned_remainder: plan.trim() || null,
        response_latency_ms: Date.now() - startRef.current,
      });
      setSuccess(true);
      setSubmittedCount((c) => c + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setLoading(false);
    }
  };

  const addAnother = () => {
    setSuccess(false);
    setDone("");
    setPlan("");
    setError(null);
    startRef.current = Date.now();
  };

  return (
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>Midday check-in</CardTitle>
          <CardDescription>A light recall prompt. No grading — just for tracking.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex items-start gap-2 rounded-xl bg-brand-100/60 dark:bg-brand-700/20 px-3 py-2 text-xs text-brand-800 dark:text-brand-200">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <p>
              You can submit as many midday check-ins as you like throughout the day.
              Each one is saved as a separate entry — earlier submissions are kept, not replaced.
            </p>
          </div>
          {success ? (
            <div className="flex flex-col items-center gap-4 py-8 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <p className="text-lg font-medium text-slate-900 dark:text-slate-100">
                Saved as entry #{submittedCount} today.
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Your earlier midday entries are still on record.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button variant="secondary" onClick={addAnother}>
                  Add another check-in
                </Button>
                <Button onClick={() => navigate("/dashboard")}>Back to dashboard</Button>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="done">What have you done so far today?</Label>
                <Textarea id="done" value={done} onChange={(e) => setDone(e.target.value)} required rows={4} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="plan">What do you still plan to do?</Label>
                <Textarea id="plan" value={plan} onChange={(e) => setPlan(e.target.value)} rows={3} />
              </div>
              {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
              <Button type="submit" loading={loading} size="lg">
                Submit
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      <Disclaimer />
    </Shell>
  );
}
