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

const STATUS_ERROR = "Could not read notification status";

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
      setError(e instanceof Error ? e.message : STATUS_ERROR);
    }
  }, [userId]);

  // First read, resolved here rather than via refresh() for the same reason as
  // RemindersPage: no setState reached synchronously from the effect, and a
  // late answer for a previous userId is dropped.
  useEffect(() => {
    let ignore = false;
    getPushStatus(userId).then(
      (s) => {
        if (!ignore) setStatus(s);
      },
      (e) => {
        if (!ignore) setError(e instanceof Error ? e.message : STATUS_ERROR);
      },
    );
    return () => {
      ignore = true;
    };
  }, [userId]);

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
        <CardTitle className="text-body flex items-center gap-2">
          {status?.enabled ? (
            <Bell className="h-4 w-4 text-ios-red" strokeWidth={2.5} />
          ) : (
            <BellOff className="h-4 w-4 text-label-3" strokeWidth={2.5} />
          )}
          Reminder notifications
        </CardTitle>
        <CardDescription>
          Get prompted to check your memory even when CogniSense isn't open.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {blocker && (
          <p className="flex items-start gap-2 rounded-xl bg-ios-orange/12 px-4 py-3 text-subhead text-label">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-ios-orange" />
            {blocker}
          </p>
        )}

        {status && !blocker && (
          <dl className="grid grid-cols-2 gap-3 text-subhead">
            <div>
              <dt className="text-caption font-semibold uppercase text-label-2">
                Status
              </dt>
              <dd className="font-medium text-label">
                {status.enabled
                  ? `On · ${status.devices} device${status.devices === 1 ? "" : "s"}`
                  : "Off"}
              </dd>
            </div>
            <div>
              <dt className="text-caption font-semibold uppercase text-label-2">
                At most
              </dt>
              <dd className="font-medium text-label">
                one every {status.cooldown_hours}h
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-caption font-semibold uppercase text-label-2">
                Quiet hours
              </dt>
              <dd className="text-label">
                {status.quiet_hours}
                {!status.currently_awake && " — quiet right now"}
              </dd>
            </div>
          </dl>
        )}

        {status && !status.scheduler_running && (
          <p className="rounded-xl bg-ios-orange/12 px-4 py-3 text-footnote text-label">
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

        {error && <p className="text-subhead text-danger">{error}</p>}
        {note && <p className="text-subhead text-success">{note}</p>}

        <p className="text-footnote text-label-2">
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
