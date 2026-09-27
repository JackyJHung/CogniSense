import { Info } from "lucide-react";

/* On every screen and report. Styled as an iOS footnote cell: quiet enough to
 * sit under any content, never so quiet that it disappears. */
export function Disclaimer() {
  return (
    <aside className="mt-8 flex items-start gap-3 rounded-2xl bg-surface px-4 py-3.5 text-footnote text-label-2">
      <Info aria-hidden="true" className="mt-px h-4 w-4 shrink-0 text-ios-orange" strokeWidth={2.25} />
      <p>
        CogniSense is a self-tracking tool, <strong className="font-semibold text-label">not</strong> a
        medical diagnostic device. Any output is a suggestion based on population-level research,
        not professional advice. If you notice worsening memory concerns, please consult a licensed
        physician.
      </p>
    </aside>
  );
}
