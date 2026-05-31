import { cn } from "@/lib/cn";

export type DotStatus = "up" | "down" | "open" | "acknowledged" | "resolved" | "closed" | "unknown";

// Status -> semantic tone. up=ok, down=danger, open=danger, acknowledged=warn,
// resolved/closed=muted, unknown=muted.
const STATUS_TONE: Record<DotStatus, string> = {
  up: "bg-ok shadow-[0_0_8px_-1px_var(--color-ok)]",
  down: "bg-danger shadow-[0_0_8px_-1px_var(--color-danger)]",
  open: "bg-danger shadow-[0_0_8px_-1px_var(--color-danger)]",
  acknowledged: "bg-warn shadow-[0_0_8px_-1px_var(--color-warn)]",
  resolved: "bg-muted",
  closed: "bg-muted",
  unknown: "bg-muted",
};

const STATUS_TEXT: Record<DotStatus, string> = {
  up: "text-ok",
  down: "text-danger",
  open: "text-danger",
  acknowledged: "text-warn",
  resolved: "text-text-dim",
  closed: "text-text-dim",
  unknown: "text-text-dim",
};

export interface StatusDotProps {
  status: DotStatus;
  pulse?: boolean;
  label?: string;
  className?: string;
}

export function StatusDot({ status, pulse = false, label, className }: StatusDotProps) {
  const dot = (
    <span
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        STATUS_TONE[status],
        pulse && "animate-pulse-dot",
      )}
      aria-hidden={label ? "true" : undefined}
    />
  );

  if (!label) {
    return (
      <span className={cn("inline-flex", className)} role="status" aria-label={`Status: ${status}`}>
        {dot}
      </span>
    );
  }

  return (
    <span
      className={cn("inline-flex items-center gap-2", className)}
      role="status"
      aria-label={`Status: ${status}`}
    >
      {dot}
      <span className={cn("text-xs font-medium uppercase tracking-wide", STATUS_TEXT[status])}>
        {label}
      </span>
    </span>
  );
}
