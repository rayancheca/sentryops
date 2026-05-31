import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type StatTone = "default" | "ok" | "warn" | "danger";

const TONE_VALUE: Record<StatTone, string> = {
  default: "text-text",
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
};

const TONE_ICON: Record<StatTone, string> = {
  default: "text-text-dim",
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
};

export interface StatProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: StatTone;
  icon?: ReactNode;
  className?: string;
}

export function Stat({ label, value, sub, tone = "default", icon, className }: StatProps) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-1.5 text-text-dim">
        {icon ? <span className={cn("[&_svg]:size-3.5", TONE_ICON[tone])}>{icon}</span> : null}
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <span className={cn("tabular text-3xl font-semibold leading-none", TONE_VALUE[tone])}>
        {value}
      </span>
      {sub ? <span className="text-xs text-text-dim">{sub}</span> : null}
    </div>
  );
}
