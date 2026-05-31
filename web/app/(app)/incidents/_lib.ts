// Shared helpers + display maps for the incident surfaces. Pure and typed.

import type { BadgeProps } from "@/components/ui";
import type { DotStatus } from "@/components/ui";
import type { Incident, IncidentStatus } from "@/lib/types";

/** Status tab values for the list filter. "all" is a UI-only sentinel. */
export type StatusFilter = "all" | IncidentStatus;

export const STATUS_TABS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

// Incident status -> StatusDot status. open/ack map to their own dot tones;
// resolved/closed are muted.
export const STATUS_DOT: Record<IncidentStatus, DotStatus> = {
  open: "open",
  acknowledged: "acknowledged",
  resolved: "resolved",
  closed: "closed",
};

// Incident status -> Badge variant. open=danger, ack=warn, resolved/closed muted.
export const STATUS_BADGE: Record<IncidentStatus, NonNullable<BadgeProps["variant"]>> = {
  open: "danger",
  acknowledged: "warn",
  resolved: "default",
  closed: "outline",
};

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  open: "OPEN",
  acknowledged: "ACK",
  resolved: "RESOLVED",
  closed: "CLOSED",
};

/** Build the list endpoint for a given status filter. */
export function incidentsEndpoint(filter: StatusFilter): string {
  return filter === "all" ? "/incidents" : `/incidents?status=${filter}`;
}

/**
 * Time-to-acknowledge in seconds (opened → acknowledged), or null when the
 * incident was never acknowledged.
 */
export function timeToAck(incident: Incident): number | null {
  if (!incident.acknowledged_at) return null;
  return diffSeconds(incident.opened_at, incident.acknowledged_at);
}

/**
 * Time-to-resolve in seconds (opened → resolved), or null when still open.
 */
export function timeToResolve(incident: Incident): number | null {
  if (!incident.resolved_at) return null;
  return diffSeconds(incident.opened_at, incident.resolved_at);
}

function diffSeconds(fromIso: string, toIso: string): number | null {
  const from = Date.parse(fromIso);
  const to = Date.parse(toIso);
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.max(0, (to - from) / 1000);
}
