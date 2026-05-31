import { Loader2 } from "lucide-react";

import { cn } from "@/lib/cn";

export interface SpinnerProps {
  /** Pixel size of the spinner glyph. */
  size?: number;
  className?: string;
  label?: string;
}

export function Spinner({ size = 20, className, label = "Loading" }: SpinnerProps) {
  return (
    <span role="status" aria-live="polite" className={cn("inline-flex", className)}>
      <Loader2 className="animate-spin text-accent" size={size} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}
