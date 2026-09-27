import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/* Apple's button styles. primary is the filled capsule apple.com and iOS use
 * for the one main action; secondary is iOS's gray "bordered" button with
 * tinted text; ghost is a plain text button; danger is destructive. Pressed
 * buttons dim, as iOS controls do, rather than moving. */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover",
  secondary: "bg-fill text-link hover:bg-fill-2",
  ghost: "bg-transparent text-link hover:bg-fill-2",
  danger: "bg-fill text-danger hover:bg-fill-2",
};

// md and lg meet Apple's 44pt minimum hit target; lg is iOS's 50pt large button.
const sizes: Record<Size, string> = {
  sm: "h-8 px-3.5 text-subhead",
  md: "h-11 px-5 text-body",
  lg: "h-[50px] px-7 text-body",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 rounded-full font-semibold",
        "transition-[background-color,opacity] duration-150 active:opacity-70",
        "outline-none focus-visible:ring-[3px] focus-visible:ring-tint/50",
        "disabled:pointer-events-none disabled:opacity-40",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      )}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
