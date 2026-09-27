import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/* The inset grouped list of iOS Settings: rows on one rounded surface, split
 * by hairlines that start where the text does, each led by a white glyph on a
 * coloured rounded square. */

type Tone = "blue" | "green" | "red" | "orange" | "yellow" | "indigo" | "purple" | "pink" | "teal" | "gray";

const TONES: Record<Tone, string> = {
  blue: "bg-ios-blue",
  green: "bg-ios-green",
  red: "bg-ios-red",
  orange: "bg-ios-orange",
  yellow: "bg-ios-yellow",
  indigo: "bg-ios-indigo",
  purple: "bg-ios-purple",
  pink: "bg-ios-pink",
  teal: "bg-ios-teal",
  gray: "bg-ios-gray",
};

export function IconTile({ icon: Icon, tone, className }: { icon: LucideIcon; tone: Tone; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[7px]", TONES[tone], className)}
    >
      <Icon className="h-[18px] w-[18px] text-white" strokeWidth={2.25} />
    </span>
  );
}

export function GroupedList({
  header,
  footer,
  children,
  className,
}: {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("mt-8 first:mt-0", className)}>
      {header && <h2 className="px-4 pb-1.5 text-footnote uppercase text-label-2">{header}</h2>}
      <ul className="overflow-hidden rounded-2xl bg-surface">{children}</ul>
      {footer && <p className="px-4 pt-1.5 text-footnote text-label-2">{footer}</p>}
    </section>
  );
}

interface ListRowProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned secondary text, as in "Wi-Fi ....... Home". */
  value?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  to?: string;
  onClick?: () => void;
  destructive?: boolean;
}

export function ListRow({ title, subtitle, value, icon, tone = "blue", to, onClick, destructive }: ListRowProps) {
  const interactive = Boolean(to || onClick);
  const body = (
    <>
      {icon && <IconTile icon={icon} tone={tone} />}
      <span
        className={cn(
          "flex min-h-11 min-w-0 flex-1 items-center gap-3 py-2.5 pr-4",
          "border-b-[0.5px] border-separator group-last:border-b-0",
        )}
      >
        <span className="min-w-0 flex-1">
          <span className={cn("block text-body", destructive ? "text-danger" : "text-label")}>{title}</span>
          {subtitle && <span className="mt-0.5 block text-subhead text-label-2">{subtitle}</span>}
        </span>
        {value != null && <span className="shrink-0 text-body text-label-2 tabular-nums">{value}</span>}
        {to && (
          <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-label-3" strokeWidth={2.75} />
        )}
      </span>
    </>
  );
  const row = cn(
    "flex w-full items-center gap-3 pl-4 text-left",
    interactive && "transition-colors hover:bg-fill-2 active:bg-fill outline-none focus-visible:bg-fill",
  );
  return (
    <li className="group">
      {to ? (
        <Link to={to} className={row}>
          {body}
        </Link>
      ) : onClick ? (
        <button type="button" onClick={onClick} className={row}>
          {body}
        </button>
      ) : (
        <div className={row}>{body}</div>
      )}
    </li>
  );
}
