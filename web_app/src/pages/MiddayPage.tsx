import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent } from "@/components/ui/Card";
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
    <Shell
      title="Midday check-in"
      back={{ to: "/dashboard", label: "Today" }}
      subtitle="A light recall prompt. No grading, just for tracking."
    >
      {success ? (
        <Card className="flex flex-col items-center px-6 py-10 text-center">
          <span className="flex h-16 w-16 items-center justify-center rounded-full bg-ios-green text-white">
            <Check aria-hidden="true" className="h-9 w-9" strokeWidth={3} />
          </span>
          <p className="mt-4 text-title3 font-semibold text-label">Saved as entry #{submittedCount} today.</p>
          <p className="mt-1 text-subhead text-label-2">Your earlier midday entries are still on record.</p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button variant="secondary" onClick={addAnother}>
              Add Another
            </Button>
            <Button onClick={() => navigate("/dashboard")}>Done</Button>
          </div>
        </Card>
      ) : (
        <form onSubmit={submit}>
          <Card>
            <CardContent className="flex flex-col gap-4 pt-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="done">What have you done so far today?</Label>
                <Textarea id="done" value={done} onChange={(e) => setDone(e.target.value)} required rows={4} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="plan">What do you still plan to do?</Label>
                <Textarea id="plan" value={plan} onChange={(e) => setPlan(e.target.value)} rows={3} />
              </div>
            </CardContent>
          </Card>
          <p className="px-4 pt-1.5 text-footnote text-label-2">
            You can submit as many midday check-ins as you like. Each is saved as a separate
            entry; earlier ones are kept, not replaced.
          </p>
          {error && <p className="mt-3 px-1 text-subhead text-danger">{error}</p>}
          <Button type="submit" loading={loading} size="lg" className="mt-5 w-full sm:w-auto">
            Submit
          </Button>
        </form>
      )}
      <Disclaimer />
    </Shell>
  );
}
