import { cn } from "@/lib/utils";

/* iOS's segmented control: a gray track, the selected segment raised on it.
 * Each segment is a toggle button (aria-pressed), so a screen reader announces
 * which one is chosen. */
export function SegmentedControl<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex shrink-0 rounded-[9px] bg-fill p-[2px]">
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-7 min-w-[4.5rem] rounded-[7px] px-3 text-footnote font-semibold text-label transition",
              "outline-none focus-visible:ring-[3px] focus-visible:ring-tint/50",
              selected
                ? "bg-selected shadow-[0_3px_8px_rgb(0_0_0/0.12),0_3px_1px_rgb(0_0_0/0.04)]"
                : "hover:bg-fill-2",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
