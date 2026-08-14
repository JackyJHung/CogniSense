import { ShieldAlert } from "lucide-react";

export function Disclaimer() {
  return (
    <div className="mt-8 flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-50/60 dark:bg-amber-500/5 px-4 py-3 text-xs leading-relaxed text-amber-900/80 dark:text-amber-200/80">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <p>
        CogniSense is a self-tracking tool, <strong>not</strong> a medical diagnostic device. Any output
        is a suggestion based on population-level research, not professional advice. If you notice
        worsening memory concerns, please consult a licensed physician.
      </p>
    </div>
  );
}
