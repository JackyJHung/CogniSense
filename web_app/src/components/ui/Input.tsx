import {
  forwardRef,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

/* iOS text fields: a borderless gray fill, 44pt tall. A focused field gets
 * macOS's soft tinted focus ring -- iOS draws none, but on the web a visible
 * focus state is not optional. */
const base =
  "w-full rounded-[10px] border-0 bg-fill px-3.5 text-body text-label placeholder:text-label-3 " +
  "outline-none transition-shadow focus:ring-[3px] focus:ring-tint/40 " +
  "disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(base, "h-11", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(base, "min-h-28 resize-y py-2.5 leading-snug", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";

// The chevrons are the `select-chevrons` class in index.css rather than
// arbitrary bg-[...] utilities: tailwind-merge cannot tell an unlabelled
// bg-[position] from a background colour, and dropped the field's fill for it.
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(base, "select-chevrons h-11 appearance-none pr-9", className)}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";
