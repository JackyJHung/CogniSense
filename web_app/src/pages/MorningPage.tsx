import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ImageIcon, Lock } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent } from "@/components/ui/Card";
import { GroupedList, ListRow } from "@/components/ui/List";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Input";
import { Disclaimer } from "@/components/Disclaimer";
import { api, ApiError, type MorningCheckin } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const TODAY = { to: "/dashboard", label: "Today" };

type ConflictDetail = {
  code?: string;
  message?: string;
  existing?: MorningCheckin;
};

export function MorningPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
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
  }, [user]);

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
      setResult(morning);
    } catch (err) {
      // Handle the "already submitted today" race condition
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail() as ConflictDetail | null;
        if (detail?.existing) {
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
      <Shell title="Morning check-in" back={TODAY}>
        <div className="h-48 animate-pulse rounded-2xl bg-fill-2" />
      </Shell>
    );
  }

  if (!result) {
    return (
      <Shell
        title="Morning check-in"
        back={TODAY}
        subtitle="List what you plan to do today, one per line. Then you'll see five things to remember for tonight's test."
      >
        <form onSubmit={submit}>
          <Card>
            <CardContent className="pt-4">
              <Textarea
                aria-label="Today's plans"
                placeholder={"e.g.\nMorning walk in the park\nGrocery shopping\nCall Mom\nFinish chapter 3"}
                rows={7}
                value={plans}
                onChange={(e) => setPlans(e.target.value)}
                required
                minLength={3}
              />
            </CardContent>
          </Card>
          <p className="px-4 pt-1.5 text-footnote text-label-2">
            You can submit once per day, so make the list complete first.
          </p>
          {error && <p className="mt-3 px-1 text-subhead text-danger">{error}</p>}
          <Button type="submit" loading={loading} size="lg" className="mt-5 w-full sm:w-auto">
            Submit & show associations
          </Button>
        </form>
        <Disclaimer />
      </Shell>
    );
  }

  return (
    <Shell
      title={alreadySubmitted ? "Today's morning check-in" : "Remember these"}
      back={TODAY}
      subtitle="Tonight we'll show you each cue word and ask you to name the object."
    >
      {alreadySubmitted && (
        <GroupedList
          className="mb-8"
          header="Your plans for today"
          footer={`Submitted at ${new Date(result.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}. You can come back to review these at any time today, but you can't submit again until tomorrow.`}
        >
          <ListRow
            icon={Lock}
            tone="green"
            title="Locked for today"
            subtitle={<span className="whitespace-pre-line">{result.planned_activities}</span>}
          />
        </GroupedList>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {result.presented_associations.map((a, i) => (
          <motion.div
            key={a.id}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
          >
            <Card className="overflow-hidden">
              <div className="flex h-28 items-center justify-center bg-gradient-to-b from-ios-blue/12 to-ios-indigo/8">
                <ImageIcon aria-hidden="true" className="h-9 w-9 text-ios-blue/60" strokeWidth={1.5} />
              </div>
              <div className="px-4 py-3">
                <p className="text-caption font-semibold uppercase text-label-2">Cue</p>
                <p className="text-body text-label">&ldquo;{a.cue_word}&rdquo;</p>
                <p className="mt-2 text-caption font-semibold uppercase text-label-2">Object</p>
                <p className="text-title3 font-semibold text-label">{a.object_name}</p>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
      <Button onClick={() => navigate("/dashboard")} className="mt-8 w-full sm:w-auto" size="lg">
        Done
      </Button>

      <Disclaimer />
    </Shell>
  );
}
