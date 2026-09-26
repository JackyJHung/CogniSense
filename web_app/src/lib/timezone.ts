/* The device's IANA time zone, as the browser reports it.
 *
 * The server counts a user's check-in day, and the quiet hours for reminders,
 * in their stored zone (backend/app/timezones.py). What the device reports is
 * only ever a suggestion: signup records it, login and turning on notifications
 * fill it in for an account that has none, and only the Settings page changes
 * a zone that is already set. */

export function deviceTimeZone(): string | null {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // ICU answers "Etc/Unknown" when it cannot tell. That is not a zone.
    return zone && zone !== "Etc/Unknown" ? zone : null;
  } catch {
    return null;
  }
}

/** Zones for the Settings picker: every one this browser knows, plus any
 *  given extras (the saved zone may be a legacy alias the list omits). */
export function timeZoneChoices(...extras: (string | null | undefined)[]): string[] {
  let known: string[] = [];
  try {
    known = Intl.supportedValuesOf("timeZone");
  } catch {
    /* older browser: the extras and UTC still make a usable list */
  }
  const all = new Set([...known, "UTC", ...extras.filter((z): z is string => !!z)]);
  return [...all].sort((a, b) => a.localeCompare(b));
}
