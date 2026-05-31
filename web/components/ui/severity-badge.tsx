import type { Severity } from "@/lib/types";

import { Badge, type BadgeProps } from "./badge";

// Severity color map per design direction:
// low=info, medium=warn, high=danger, critical=critical.
const SEVERITY_VARIANT: Record<Severity, NonNullable<BadgeProps["variant"]>> = {
  low: "info",
  medium: "warn",
  high: "danger",
  critical: "critical",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  low: "LOW",
  medium: "MED",
  high: "HIGH",
  critical: "CRIT",
};

export interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  return (
    <Badge
      variant={SEVERITY_VARIANT[severity]}
      className={className}
      aria-label={`Severity: ${severity}`}
    >
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}
