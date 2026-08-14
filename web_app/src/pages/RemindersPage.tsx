import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Check, ImagePlus, ListChecks, Plus, Sparkles } from "lucide-react";
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

export function RemindersPage() {
  const navigate = useNavigate();
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

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const [list, sc] = await Promise.all([
        api.get<ReminderItem[]>(`/reminders/${user.id}`),
        api.get<ProspectiveScore>(`/reminders/${user.id}/prospective-score`),
      ]);
      setItems(list);
      setScore(sc);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reminders");
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

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
    <Shell>
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Button>

      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Things to remember
        </h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Save what you mean to do. Later we'll ask what you remember — and then
          show you the list either way.
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {/* ---------------- LIST ---------------- */}
      {phase === "list" && (
        <div className="space-y-6">
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
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  If you add a photo, give it a short name too — we need words to
                  compare against what you remember.
                </p>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="photo">Photo (optional)</Label>
                <input
                  id="photo"
                  type="file"
                  accept="image/*"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-slate-600 dark:text-slate-400 file:mr-4 file:rounded-lg file:border-0 file:bg-brand-500/10 file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-700 dark:file:text-brand-300"
                />
                {file && (
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                    <ImagePlus className="h-3.5 w-3.5" /> {file.name}
                  </p>
                )}
              </div>
              <Button onClick={addItem} loading={busy} disabled={!draft.trim() && !draftLabel.trim()}>
                <Plus className="h-4 w-4" /> Save it
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Your list</CardTitle>
                <CardDescription>
                  {pending.length === 0
                    ? "Nothing outstanding right now."
                    : `${pending.length} thing${pending.length === 1 ? "" : "s"} to do.`}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {pending.length > 0 && (
                <ul className="space-y-2">
                  {pending.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-start gap-3 rounded-xl bg-white/40 dark:bg-white/[0.03] px-4 py-3 ring-1 ring-slate-200/40 dark:ring-white/5"
                    >
                      <ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                      <span className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                        {itemText(item)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Button
                className="mt-4"
                onClick={startCheck}
                loading={busy}
                disabled={pending.length === 0}
              >
                <Sparkles className="h-4 w-4" /> Test me now
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
              <CardTitle>{check.prompt}</CardTitle>
              <CardDescription>
                You have {check.n_items_active} thing
                {check.n_items_active === 1 ? "" : "s"} saved. Write down whatever
                comes to mind — one is enough.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                value={recall}
                onChange={(e) => setRecall(e.target.value)}
                placeholder="What did you mean to do?"
                autoFocus
              />
              <div className="flex gap-2">
                <Button onClick={submitRecall} loading={busy}>
                  Done
                </Button>
                <Button variant="ghost" onClick={submitRecall} loading={busy}>
                  I can't remember — just show me
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* ---------------- RESULT + the aid ---------------- */}
      {phase === "result" && result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <Card
            className={
              result.passed
                ? "border-emerald-500/40 bg-emerald-50/60 dark:bg-emerald-500/10"
                : "border-sky-500/40 bg-sky-50/60 dark:bg-sky-500/10"
            }
          >
            <CardContent className="pt-6">
              <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200">
                {result.feedback}
              </p>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Remembered {result.n_recalled} of {result.n_active}. One check on its
                own doesn't mean anything — the pattern over weeks is what matters.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Your list</CardTitle>
              <CardDescription>Tick anything you've already done.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {result.items.map((item) => {
                  const matched = result.matches.find((m) => m.item_id === item.id)?.matched;
                  const isSelected = selected.includes(item.id);
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() =>
                          setSelected((s) =>
                            s.includes(item.id) ? s.filter((x) => x !== item.id) : [...s, item.id],
                          )
                        }
                        className={`flex w-full items-start gap-3 rounded-xl px-4 py-3 text-left ring-1 transition ${
                          isSelected
                            ? "bg-emerald-500/10 ring-emerald-500/40"
                            : "bg-white/40 dark:bg-white/[0.03] ring-slate-200/40 dark:ring-white/5"
                        }`}
                      >
                        <span
                          className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                            isSelected
                              ? "border-emerald-500 bg-emerald-500 text-white"
                              : "border-slate-300 dark:border-white/20"
                          }`}
                        >
                          {isSelected && <Check className="h-3 w-3" />}
                        </span>
                        <span className="flex-1 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                          {itemText(item)}
                        </span>
                        {matched && (
                          <span className="shrink-0 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                            you said this
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-4 flex gap-2">
                <Button onClick={markDone} loading={busy} disabled={selected.length === 0}>
                  <Check className="h-4 w-4" /> Mark {selected.length || ""} done
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
            </CardContent>
          </Card>

          <p className="rounded-xl bg-slate-900/[0.03] dark:bg-white/[0.03] px-4 py-3 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            {result.memory_aid_disclaimer}
          </p>
        </motion.div>
      )}

      <Disclaimer />
    </Shell>
  );
}

function ScoreCard({ score }: { score: ProspectiveScore }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">How you've been doing</CardTitle>
        <CardDescription>
          Across {score.n_checks} check{score.n_checks === 1 ? "" : "s"}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {score.recall_rate == null ? (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {score.trend_note ?? "No checks answered yet."}
          </p>
        ) : (
          <>
            <p className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              {Math.round(score.recall_rate * 100)}%
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {score.recall_rate_ci_low != null && score.recall_rate_ci_high != null
                ? `of your reminders recalled unprompted (95% range ${Math.round(
                    score.recall_rate_ci_low * 100,
                  )}–${Math.round(score.recall_rate_ci_high * 100)}%)`
                : "of your reminders recalled unprompted — too few checks for a range yet"}
            </p>
            {score.trend_note && (
              <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {score.trend_note}
                {score.trend_available &&
                  score.change_pct != null &&
                  score.change_ci_low_pct != null &&
                  score.change_ci_high_pct != null && (
                    <span className="block mt-1 text-xs text-slate-500 dark:text-slate-500">
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
        <p className="mt-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {score.memory_aid_disclaimer}
        </p>
      </CardContent>
    </Card>
  );
}
