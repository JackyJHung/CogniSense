import type { LabelHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/* A field's name sits above it in footnote size, like an iOS section header. */
export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("px-1 text-footnote text-label-2", className)} {...props} />;
}
