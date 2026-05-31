"use client";

import { CheckCircle2, Clock, Siren, Timer } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import {
  Badge,
  Card,
  CardContent,
  EmptyState,
  PageHeader,
  SeverityBadge,
  Skeleton,
  Stat,
  StatusDot,
  Table,
  Tabs,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { ApiError, fetcher } from "@/lib/api";
import { formatDuration, formatRelative } from "@/lib/format";
import type { Incident, MttaMttr, Page } from "@/lib/types";

import {
  incidentsEndpoint,
  STATUS_BADGE,
  STATUS_DOT,
  STATUS_LABEL,
  STATUS_TABS,
  timeToAck,
  timeToResolve,
  type StatusFilter,
} from "./_lib";

export default function IncidentsPage() {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const list = useSWR<Page<Incident>>(incidentsEndpoint(filter), fetcher);
  const metrics = useSWR<MttaMttr>("/incidents/metrics/mtta-mttr", fetcher);

  const incidents = list.data?.items ?? [];

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <PageHeader
        title="Incidents"
        description="Detection-to-resolution timeline for every service incident, with org-wide response metrics."
      />

      <MetricsRow query={metrics} totalOpen={openCount(incidents, list.data?.total)} />

      <div className="flex items-center justify-between gap-3">
        <Tabs tabs={STATUS_TABS} value={filter} onValueChange={setFilter} />
        {list.data ? (
          <span className="tabular text-xs text-text-dim">
            {list.data.total} incident{list.data.total === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      <Card className="overflow-hidden">
        <IncidentTable query={list} />
      </Card>
    </div>
  );
}

function openCount(incidents: Incident[], total?: number): number | undefined {
  // Best-effort: when viewing the "all"/other tab we cannot know the open count
  // precisely from the page, so leave it undefined unless the rows make it clear.
  if (total === undefined) return undefined;
  return incidents.filter((i) => i.status === "open").length || undefined;
}

// --------------------------------------------------------------------------- //
// Org response metrics
// --------------------------------------------------------------------------- //
function MetricsRow({
  query,
  totalOpen,
}: {
  query: ReturnType<typeof useSWR<MttaMttr>>;
  totalOpen?: number;
}) {
  const { data, isLoading, error } = query;

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Card>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-14 w-full" />
          ) : (
            <Stat
              label="MTTA · acknowledge"
              value={data?.mtta_seconds != null ? formatDuration(data.mtta_seconds) : "—"}
              tone={mttaTone(data?.mtta_seconds)}
              icon={<Clock />}
              sub="Mean time to acknowledge"
            />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-14 w-full" />
          ) : (
            <Stat
              label="MTTR · resolve"
              value={data?.mttr_seconds != null ? formatDuration(data.mttr_seconds) : "—"}
              tone={mttrTone(data?.mttr_seconds)}
              icon={<Timer />}
              sub="Mean time to resolve"
            />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Stat
            label="Currently open"
            value={totalOpen ?? "—"}
            tone={totalOpen && totalOpen > 0 ? "danger" : "ok"}
            icon={<Siren />}
            sub={error ? "Metrics unavailable" : "Awaiting acknowledgement or resolution"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

const MTTA_WARN_SECONDS = 5 * 60; // 5m
const MTTA_DANGER_SECONDS = 15 * 60; // 15m
const MTTR_WARN_SECONDS = 60 * 60; // 1h
const MTTR_DANGER_SECONDS = 4 * 60 * 60; // 4h

function mttaTone(seconds?: number | null): "ok" | "warn" | "danger" {
  if (seconds == null) return "ok";
  if (seconds >= MTTA_DANGER_SECONDS) return "danger";
  if (seconds >= MTTA_WARN_SECONDS) return "warn";
  return "ok";
}

function mttrTone(seconds?: number | null): "ok" | "warn" | "danger" {
  if (seconds == null) return "ok";
  if (seconds >= MTTR_DANGER_SECONDS) return "danger";
  if (seconds >= MTTR_WARN_SECONDS) return "warn";
  return "ok";
}

// --------------------------------------------------------------------------- //
// Incident table
// --------------------------------------------------------------------------- //
function IncidentTable({ query }: { query: ReturnType<typeof useSWR<Page<Incident>>> }) {
  const { data, error, isLoading } = query;

  if (isLoading) {
    return (
      <div className="divide-y divide-border">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-4">
            <Skeleton className="h-5 w-12" />
            <Skeleton className="h-4 w-64" />
            <Skeleton className="ml-auto h-4 w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={<Siren />}
        title="Could not load incidents"
        description={error instanceof ApiError ? error.message : "Unexpected error."}
      />
    );
  }

  const incidents = data?.items ?? [];
  if (incidents.length === 0) {
    return (
      <EmptyState
        icon={<CheckCircle2 />}
        title="No incidents"
        description="Nothing matches this filter. Quiet is good."
      />
    );
  }

  return (
    <Table>
      <THead sticky>
        <TR className="hover:bg-transparent">
          <TH className="w-px">Sev</TH>
          <TH>Incident</TH>
          <TH className="w-px whitespace-nowrap">Status</TH>
          <TH className="w-px whitespace-nowrap text-right">Opened</TH>
          <TH className="w-px whitespace-nowrap text-right">MTTA</TH>
          <TH className="w-px whitespace-nowrap text-right">MTTR</TH>
        </TR>
      </THead>
      <TBody>
        {incidents.map((incident) => (
          <IncidentRow key={incident.id} incident={incident} />
        ))}
      </TBody>
    </Table>
  );
}

function IncidentRow({ incident }: { incident: Incident }) {
  const ack = timeToAck(incident);
  const resolve = timeToResolve(incident);

  return (
    <TR className="cursor-pointer">
      <TD>
        <SeverityBadge severity={incident.severity} />
      </TD>
      <TD>
        <Link
          href={`/incidents/${incident.id}`}
          className="group flex flex-col gap-0.5 focus-visible:outline-none"
        >
          <span className="font-medium text-text underline-offset-4 group-hover:text-accent group-hover:underline group-focus-visible:text-accent group-focus-visible:underline">
            {incident.title}
          </span>
          <span className="tabular text-xs text-text-dim">#{incident.id.slice(0, 8)}</span>
        </Link>
      </TD>
      <TD>
        <span className="inline-flex items-center gap-2">
          <StatusDot status={STATUS_DOT[incident.status]} pulse={incident.status === "open"} />
          <Badge variant={STATUS_BADGE[incident.status]}>{STATUS_LABEL[incident.status]}</Badge>
        </span>
      </TD>
      <TD className="text-right">
        <span className="tabular text-xs text-text-dim" title={incident.opened_at}>
          {formatRelative(incident.opened_at)}
        </span>
      </TD>
      <TD className="tabular text-right text-xs text-text-dim">
        {ack != null ? formatDuration(ack) : "—"}
      </TD>
      <TD className="tabular text-right text-xs text-text-dim">
        {resolve != null ? formatDuration(resolve) : "—"}
      </TD>
    </TR>
  );
}
