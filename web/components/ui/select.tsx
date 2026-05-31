import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => (
    <div className="relative inline-flex w-full items-center">
      <select
        ref={ref}
        className={cn(
          "h-10 w-full appearance-none rounded-md border border-border bg-surface pl-3 pr-9 text-sm text-text",
          "transition-colors duration-[140ms]",
          "hover:border-accent-dim/60",
          "focus-visible:ring-accent/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 size-4 text-text-dim"
        aria-hidden="true"
      />
    </div>
  ),
);
Select.displayName = "Select";
