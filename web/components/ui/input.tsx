import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-text",
        "placeholder:text-muted",
        "transition-colors duration-[140ms]",
        "hover:border-accent-dim/60",
        "focus-visible:ring-accent/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        type === "number" && "tabular",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
