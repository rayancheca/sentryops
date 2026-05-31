"use client";

import {
  BrainCircuit,
  CheckCircle2,
  CircleDot,
  Lock,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { EmptyState } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import type { IncidentEvent } from "@/lib/types";

// event_type (see backend IncidentEventType) -> icon + tone + readable title.
interface EventStyle {
  icon: LucideIcon;
  ring: string;
  iconColor: string;
  title: string;
}

const EVENT_STYLES: Record<string, EventStyle> = {
  opened: {
    icon: CircleDot,
    ring: "border-danger/40 bg-danger/10",
    iconColor: "text-danger",
    title: "Incident opened",
  },
  ai_triaged: {
    icon: BrainCircuit,
    ring: "border-accent/40 bg-accent/10",
    iconColor: "text-accent",
    title: "AI triage completed",
  },
  acknowledged: {
    icon: ShieldCheck,
    ring: "border-warn/40 bg-warn/10",
    iconColor: "text-warn",
    title: "Acknowledged",
  },
  comment: {
    icon: MessageSquare,
    ring: "border-border bg-surface-2",
    iconColor: "text-text-dim",
    title: "Comment",
  },
  resolved: {
    icon: CheckCircle2,
    ring: "border-ok/40 bg-ok/10",
    iconColor: "text-ok",
    title: "Resolved",
  },
  closed: {
    icon: Lock,
    ring: "border-border bg-surface-2",
    iconColor: "text-text-dim",
    title: "Closed",
  },
  recovered: {
    icon: RotateCcw,
    ring: "border-ok/40 bg-ok/10",
    iconColor: "text-ok",
    title: "Service recovered",
  },
};

const FALLBACK_STYLE: EventStyle = {
  icon: CircleDot,
  ring: "border-border bg-surface-2",
  iconColor: "text-text-dim",
  title: "Event",
};

export function Timeline({ events }: { events: IncidentEvent[] }) {
  if (events.length === 0) {
    return <EmptyState title="No events yet" description="Lifecycle events will appear here." />;
  }

  // Chronological: oldest first so the story reads top-to-bottom.
  const ordered = [...events].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));

  return (
    <ol className="relative space-y-1" role="list">
      {ordered.map((event, index) => (
        <TimelineItem key={event.id} event={event} isLast={index === ordered.length - 1} />
      ))}
    </ol>
  );
}

function TimelineItem({ event, isLast }: { event: IncidentEvent; isLast: boolean }) {
  const style = EVENT_STYLES[event.event_type] ?? FALLBACK_STYLE;
  const Icon = style.icon;
  const title = EVENT_STYLES[event.event_type]?.title ?? humanize(event.event_type);

  return (
    <li className="relative flex gap-3 pb-4">
      {!isLast ? (
        <span
          className="absolute left-[15px] top-8 h-[calc(100%-1rem)] w-px bg-border"
          aria-hidden="true"
        />
      ) : null}
      <span
        className={cn(
          "relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border [&_svg]:size-4",
          style.ring,
          style.iconColor,
        )}
        aria-hidden="true"
      >
        <Icon />
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-medium text-text">{title}</span>
          <span
            className="tabular shrink-0 text-xs text-text-dim"
            title={formatDateTime(event.created_at)}
          >
            {formatRelative(event.created_at)}
          </span>
        </div>
        {event.message ? (
          <p className="mt-0.5 whitespace-pre-wrap text-sm text-text-dim">{event.message}</p>
        ) : null}
      </div>
    </li>
  );
}

function humanize(eventType: string): string {
  return eventType
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
