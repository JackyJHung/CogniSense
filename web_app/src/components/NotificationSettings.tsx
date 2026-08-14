import { useCallback, useEffect, useState } from "react";
import { Bell, BellOff, Send, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import {
  describeBlocker,
  disablePush,
  enablePush,
  getPushStatus,
  sendTestPush,
  type PushStatus,
} from "@/lib/push";

export function NotificationSettings({ userId }: { userId: number }) {
  const [status, setStatus] = useState<PushStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // describeBlocker() already reports unsupported browsers as the first case.
  const blocker = describeBlocker();

  const refresh = useCallback(async () => {
    try {
      setStatus(await getPushStatus(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read notification status");
    }
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggle() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      setStatus(status?.enabled ? await disablePush(userId) : await enablePush(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change notification settings");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const r = await sendTestPush(userId);
      setNote(
        r.detail ??
          `Sent to ${r.sent} of ${r.devices} device${r.devices === 1 ? "" : "s"}. ` +
            `It should appear within a few seconds.`,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send a test notification");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          {status?.enabled ? (
            <Bell className="h-4 w-4 text-brand-500" />
          ) : (
            <BellOff className="h-4 w-4 text-slate-400" />
          )}
          Reminder notifications
        </CardTitle>
        <CardDescription>
          Get prompted to check your memory even when CogniSense isn't open.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {blocker && (
          <p className="flex items-start gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-sm leading-relaxed text-amber-900 dark:text-amber-200">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            {blocker}
          </p>
        )}

        {status && !blocker && (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Status
              </dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">
                {status.enabled
                  ? `On · ${status.devices} device${status.devices === 1 ? "" : "s"}`
                  : "Off"}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                At most
              </dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">
                one every {status.cooldown_hours}h
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Quiet hours
              </dt>
              <dd className="text-slate-700 dark:text-slate-300">
                {status.quiet_hours}
                {!status.currently_awake && " — quiet right now"}
              </dd>
            </div>
          </dl>
        )}

        {status && !status.scheduler_running && (
          <p className="rounded-xl bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-900 dark:text-amber-200">
            The reminder scheduler is switched off on the server, so scheduled
            prompts won't be sent. Test notifications still work.
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={toggle} loading={busy} disabled={!!blocker} variant={status?.enabled ? "secondary" : "primary"}>
            {status?.enabled ? (
              <>
                <BellOff className="h-4 w-4" /> Turn off on this device
              </>
            ) : (
              <>
                <Bell className="h-4 w-4" /> Turn on notifications
              </>
            )}
          </Button>
          {status?.enabled && (
            <Button variant="ghost" onClick={test} loading={busy}>
              <Send className="h-4 w-4" /> Send a test
            </Button>
          )}
        </div>

        {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        {note && <p className="text-sm text-emerald-700 dark:text-emerald-300">{note}</p>}

        <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          You can close this page and still be reminded. Two things do have to
          keep running: the CogniSense server, and your browser. On a phone the
          browser can be fully closed. On a desktop, Chrome only delivers
          notifications after you quit it if "Continue running background apps"
          is enabled in its settings.
        </p>
      </CardContent>
    </Card>
  );
}
