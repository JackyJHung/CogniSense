import { useMemo, useState, type FormEvent } from "react";
import { Globe } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, type User } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deviceTimeZone, timeZoneChoices } from "@/lib/timezone";

/** Where the user's day begins. The server counts check-in days, and the quiet
 *  hours for reminders, in this zone. Devices only ever fill in a missing one;
 *  this is the one place that changes a zone once it is set -- which is also
 *  how someone who moves, or whose browser reports the wrong zone, fixes it. */
export function TimeZoneSettings() {
  const { user, setUser } = useAuth();
  const device = deviceTimeZone();
  const saved = user?.timezone ?? null;
  const [choice, setChoice] = useState(saved ?? device ?? "UTC");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const zones = useMemo(() => timeZoneChoices(saved, device), [saved, device]);

  if (!user) return null;

  async function save(zone: string) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      setUser(await api.post<User>("/users/me/timezone", { timezone: zone }));
      setChoice(zone);
      setNote(`Saved. Your day now starts at midnight in ${label(zone)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that time zone");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void save(choice);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-body flex items-center gap-2">
          <Globe className="h-4 w-4 text-ios-blue" strokeWidth={2.5} /> Time zone
        </CardTitle>
        <CardDescription>
          Each day, and each morning check-in, starts at midnight in this time
          zone. Reminders also stay quiet overnight by it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-subhead text-label">
          {saved ? (
            <>
              Your days follow <strong>{label(saved)}</strong>.
            </>
          ) : (
            <>
              Not set yet, so your days are counted in <strong>UTC</strong>.
            </>
          )}
        </p>

        {device && device !== saved && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl bg-ios-orange/12 px-4 py-3 text-subhead text-label">
            <span>
              This device is set to <strong>{label(device)}</strong>.
            </span>
            <Button variant="secondary" size="sm" loading={busy} onClick={() => void save(device)}>
              Use {label(device)}
            </Button>
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="timezone">Choose a time zone</Label>
            <Select id="timezone" value={choice} onChange={(e) => setChoice(e.target.value)}>
              {zones.map((z) => (
                <option key={z} value={z}>
                  {label(z)}
                </option>
              ))}
            </Select>
          </div>
          {error && <p className="text-subhead text-danger">{error}</p>}
          {note && <p className="text-subhead text-success">{note}</p>}
          <Button type="submit" variant="secondary" loading={busy} disabled={choice === saved} className="sm:self-start">
            Save time zone
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function label(zone: string): string {
  return zone.replaceAll("_", " ");
}
