import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary:
    "bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-lg shadow-brand-500/25 hover:shadow-brand-500/40 hover:from-brand-400 hover:to-brand-600 active:translate-y-px",
  secondary:
    "bg-white/70 dark:bg-white/5 text-slate-900 dark:text-slate-100 border border-slate-200/80 dark:border-white/10 backdrop-blur hover:bg-white/90 dark:hover:bg-white/10",
  ghost:
    "bg-transparent text-slate-700 dark:text-slate-300 hover:bg-slate-900/5 dark:hover:bg-white/5",
  danger:
    "bg-rose-500 text-white hover:bg-rose-600 shadow-lg shadow-rose-500/20",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-12 px-6 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium",
        "transition-all duration-200 outline-none",
        "focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent",
        "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {loading && (
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
      )}
      {children}
    </button>
  )
);
Button.displayName = "Button";
