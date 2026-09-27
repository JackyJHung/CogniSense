import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, ImagePlus, Plus, Sparkles } from "lucide-react";
import { Shell } from "@/components/Shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Disclaimer } from "@/components/Disclaimer";
import { NotificationSettings } from "@/components/NotificationSettings";
import {
  api,
  type ProspectiveScore,
  type ReminderCheck,
  type ReminderItem,
  type ReminderRecallResult,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Phase = "list" | "prompt" | "result";

function itemText(item: ReminderItem): string {
  return item.description || item.label || "(untitled)";
}

function fetchReminderState(userId: number) {
  return Promise.all([
    api.get<ReminderItem[]>(`/reminders/${userId}`),
    api.get<ProspectiveScore>(`/reminders/${userId}/prospective-score`),
  ]);
}

export function RemindersPage() {
  const { user } = useAuth();

  const [items, setItems] = useState<ReminderItem[]>([]);
  const [score, setScore] = useState<ProspectiveScore | null>(null);
  const [phase, setPhase] = useState<Phase>("list");
  const [check, setCheck] = useState<ReminderCheck | null>(null);
  const [result, setResult] = useState<ReminderRecallResult | null>(null);
  const [recall, setRecall] = useState("");
  const [promptShownAt, setPromptShownAt] = useState<number | null>(null);

  const [draft, setDraft] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);

  // Re-read after each change the user makes.
  const load = useCallback(async () => {
    if (!user) return;
    try {
      const [list, sc] = await fetchReminderState(user.id);
      setItems(list);
      setScore(sc);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reminders");
    }
  }, [user]);

  // First read. Not `void load()`: state set through a callback called from an
  // effect is what react-hooks/set-state-in-effect rejects, and resolving the
  // promise here lets the ignore flag drop a response for a previous user.
  useEffect(() => {
    if (!user) return;
    let ignore = false;
    fetchReminderState(user.id).then(
      ([list, sc]) => {
        if (ignore) return;
        setItems(list);
        setScore(sc);
      },
      (e) => {
        if (!ignore) setError(e instanceof Error ? e.message : "Failed to load reminders");
      },
    );
    return () => {
      ignore = true;
    };
  }, [user]);

  if (!user) return null;

  async function addItem() {
    if (!draft.trim() && !draftLabel.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<ReminderItem>("/reminders", {
        user_id: user!.id,
        description: draft.trim() || null,
        label: draftLabel.trim() || null,
      });
      if (file) {
        const form = new FormData();
        form.append("image", file);
        await api.postForm<ReminderItem>(`/reminders/${created.id}/image`, form);
      }
      setDraft("");
      setDraftLabel("");
      setFile(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that reminder");
    } finally {
      setBusy(false);
    }
  }

  async function startCheck() {
    setBusy(true);
    setError(null);
    try {
      const c = await api.post<ReminderCheck>(`/reminders/${user!.id}/check`);
      setCheck(c);
      setRecall("");
      setPromptShownAt(Date.now());
      setPhase("prompt");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start a check");
    } finally {
      setBusy(false);
    }
  }

  async function submitRecall() {
    if (!check) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<ReminderRecallResult>(
        `/reminders/check/${check.check_id}/recall`,
        {
          recall_text: recall,
          response_latency_ms: promptShownAt ? Date.now() - promptShownAt : null,
        },
      );
      setResult(r);
      setSelected([]);
      setPhase("result");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit your answer");
    } finally {
      setBusy(false);
    }
  }

  async function markDone() {
    if (selected.length === 0) return;
    setBusy(true);
    try {
      await api.post(`/reminders/${user!.id}/done`, { item_ids: selected });
      setSelected([]);
      setPhase("list");
      setResult(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update those reminders");
    } finally {
      setBusy(false);
    }
  }

  const pending = items.filter((i) => i.status === "pending");

  return (
    <Shell
      title="Things to remember"
      subtitle="Save what you mean to do. Later we'll ask what you remember, and then show you the list either way."
    >
      {error && <p className="mb-4 px-1 text-subhead text-danger">{error}</p>}

      {/* ---------------- LIST ---------------- */}
      {phase === "list" && (
        <div className="space-y-8">
          <section>
            <h2 className="px-4 pb-1.5 text-footnote uppercase text-label-2">Your list</h2>
            <ul className="overflow-hidden rounded-2xl bg-surface">
              {pending.length === 0 ? (
                <li className="px-4 py-3 text-body text-label-2">Nothing outstanding right now.</li>
              ) : (
                pending.map((item) => (
                  <li key={item.id} className="group flex items-center gap-3 pl-4">
                    <span
                      aria-hidden="true"
                      className="h-[22px] w-[22px] shrink-0 rounded-full border-[1.5px] border-label-3"
                    />
                    <span className="flex-1 border-b-[0.5px] border-separator py-3 pr-4 text-body text-label group-last:border-b-0">
                      {itemText(item)}
                    </span>
                  </li>
                ))
              )}
            </ul>
            <p className="px-4 pt-1.5 text-footnote text-label-2">
              {pending.length === 0
                ? "Add something below, and you'll be asked about it later."
                : `${pending.length} thing${pending.length === 1 ? "" : "s"} to do. Test yourself before you look.`}
            </p>
            <Button
              className="mt-4 w-full sm:w-auto"
              onClick={startCheck}
              loading={busy}
              disabled={pending.length === 0}
            >
              <Sparkles aria-hidden="true" className="h-4 w-4" /> Test me now
            </Button>
          </section>

          <Card>
            <CardHeader>
              <CardTitle>Add something</CardTitle>
              <CardDescription>
                Type what you want to do, and add a photo if it helps you picture it.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="desc">What do you want to do?</Label>
                <Textarea
                  id="desc"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="e.g. call the dentist about the crown"
                  rows={3}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="label">Short name (optional)</Label>
                <Input
                  id="label"
                  value={draftLabel}
                  onChange={(e) => setDraftLabel(e.target.value)}
                  placeholder="e.g. dentist"
                />
                <p className="px-1 text-footnote text-label-2">
                  If you add a photo, give it a short name too: we need words to compare against
                  what you remember.
                </p>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="photo">Photo (optional)</Label>
                <input
                  id="photo"
                  type="file"
                  accept="image/*"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-subhead text-label-2 file:mr-3 file:h-8 file:rounded-full file:border-0 file:bg-fill file:px-4 file:text-subhead file:font-semibold file:text-link"
                />
                {file && (
                  <p className="flex items-center gap-1.5 px-1 text-footnote text-label-2">
                    <ImagePlus aria-hidden="true" className="h-3.5 w-3.5" /> {file.name}
                  </p>
                )}
              </div>
              <Button onClick={addItem} loading={busy} disabled={!draft.trim() && !draftLabel.trim()}>
                <Plus aria-hidden="true" className="h-4 w-4" /> Save it
              </Button>
            </CardContent>
          </Card>

          <NotificationSettings userId={user.id} />

          {score && <ScoreCard score={score} />}
        </div>
      )}

      {/* ---------------- PROMPT (no items shown) ---------------- */}
      {phase === "prompt" && check && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-title3">{check.prompt}</CardTitle>
              <CardDescription>
                You have {check.n_items_active} thing
                {check.n_items_active === 1 ? "" : "s"} saved. Write down whatever comes to mind;
                one is enough.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                aria-label="What you remember"
                value={recall}
                onChange={(e) => setRecall(e.target.value)}
                placeholder="What did you mean to do?"
                autoFocus
              />
              <div className="flex flex-wrap gap-2">
                <Button onClick={submitRecall} loading={busy}>
                  Done
                </Button>
                <Button variant="ghost" onClick={submitRecall} loading={busy}>
                  I can't remember, just show me
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* ---------------- RESULT + the aid ---------------- */}
      {phase === "result" && result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
          <Card className="flex items-start gap-3 px-4 py-3.5">
            <span
              aria-hidden="true"
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ${
                result.passed ? "bg-ios-green" : "bg-ios-blue"
              }`}
            >
              {result.passed ? (
                <Check className="h-5 w-5" strokeWidth={3} />
              ) : (
                <Sparkles className="h-5 w-5" />
              )}
            </span>
            <div>
              <p className="text-body font-semibold text-label">{result.feedback}</p>
              <p className="mt-0.5 text-subhead text-label-2">
                Remembered {result.n_recalled} of {result.n_active}. One check on its own doesn't
                mean anything; the pattern over weeks is what matters.
              </p>
            </div>
          </Card>

          <section>
            <h2 className="px-4 pb-1.5 text-footnote uppercase text-label-2">Your list</h2>
            <ul className="overflow-hidden rounded-2xl bg-surface">
              {result.items.map((item) => {
                const matched = result.matches.find((m) => m.item_id === item.id)?.matched;
                const isSelected = selected.includes(item.id);
                return (
                  <li key={item.id} className="group">
                    <button
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() =>
                        setSelected((s) =>
                          s.includes(item.id) ? s.filter((x) => x !== item.id) : [...s, item.id],
                        )
                      }
                      className="flex w-full items-center gap-3 pl-4 text-left outline-none transition-colors hover:bg-fill-2 focus-visible:bg-fill"
                    >
                      <span
                        aria-hidden="true"
                        className={`flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full ${
                          isSelected ? "bg-ios-blue text-white" : "border-[1.5px] border-label-3"
                        }`}
                      >
                        {isSelected && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                      </span>
                      <span className="flex flex-1 items-center gap-3 border-b-[0.5px] border-separator py-3 pr-4 group-last:border-b-0">
                        <span className={`flex-1 text-body ${isSelected ? "text-label-2 line-through" : "text-label"}`}>
                          {itemText(item)}
                        </span>
                        {matched && (
                          <span className="shrink-0 rounded-full bg-ios-green/15 px-2 py-0.5 text-caption font-semibold text-success">
                            You said this
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="px-4 pt-1.5 text-footnote text-label-2">Tick anything you've already done.</p>
          </section>

          <div className="flex flex-wrap gap-2">
            <Button onClick={markDone} loading={busy} disabled={selected.length === 0}>
              <Check aria-hidden="true" className="h-4 w-4" /> Mark {selected.length || ""} done
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setPhase("list");
                setResult(null);
              }}
            >
              Back to list
            </Button>
          </div>

          <p className="px-4 text-footnote text-label-2">{result.memory_aid_disclaimer}</p>
        </motion.div>
      )}

      <Disclaimer />
    </Shell>
  );
}

function ScoreCard({ score }: { score: ProspectiveScore }) {
  return (
    <Card className="px-5 py-4">
      <p className="text-subhead font-semibold text-ios-blue">How you've been doing</p>
      <p className="mt-0.5 text-footnote text-label-2">
        Across {score.n_checks} check{score.n_checks === 1 ? "" : "s"}.
      </p>
      {score.recall_rate == null ? (
        <p className="mt-3 text-subhead text-label-2">{score.trend_note ?? "No checks answered yet."}</p>
      ) : (
        <>
          <p className="mt-2 font-rounded text-large-title font-bold tracking-tight text-label tabular-nums">
            {Math.round(score.recall_rate * 100)}%
          </p>
          <p className="mt-0.5 text-footnote text-label-2">
            {score.recall_rate_ci_low != null && score.recall_rate_ci_high != null
              ? `of your reminders recalled unprompted (95% range ${Math.round(
                  score.recall_rate_ci_low * 100,
                )}–${Math.round(score.recall_rate_ci_high * 100)}%)`
              : "of your reminders recalled unprompted — too few checks for a range yet"}
          </p>
          {score.trend_note && (
            <p className="mt-3 text-subhead text-label-2">
              {score.trend_note}
              {score.trend_available &&
                score.change_pct != null &&
                score.change_ci_low_pct != null &&
                score.change_ci_high_pct != null && (
                  <span className="mt-1 block text-footnote text-label-2 tabular-nums">
                    Change vs. your earlier baseline: {score.change_pct > 0 ? "+" : ""}
                    {score.change_pct.toFixed(0)}% (95% range{" "}
                    {score.change_ci_low_pct > 0 ? "+" : ""}
                    {score.change_ci_low_pct.toFixed(0)}% to{" "}
                    {score.change_ci_high_pct > 0 ? "+" : ""}
                    {score.change_ci_high_pct.toFixed(0)}%)
                  </span>
                )}
            </p>
          )}
        </>
      )}
      <p className="mt-4 text-footnote text-label-2">{score.memory_aid_disclaimer}</p>
    </Card>
  );
}
