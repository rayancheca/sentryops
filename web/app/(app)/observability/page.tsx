"use client";

import { Activity, ChevronDown, Radio, ShieldAlert, SignalHigh } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import {
  Badge,
  Card,
  CardContent,
  EmptyState,
  PageHeader,
  Skeleton,
  Stat,
  StatusDot,
} from "@/components/ui";
import { ApiError, fetcher } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatPercent, formatRelative } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import type { Page } from "@/lib/types";

import { ServiceDetail } from "./_service-detail";
import { uptimeToScore, type StatusGridRow } from "./_types";

const STATUS_ENDPOINT = "/observability/status";

export default function ObservabilityPage() {
  const { hasRole } = useAuth();
  const canOperate = hasRole("operator");
  const { data, error, isLoading, mutate } = useSWR<Page<StatusGridRow>>(STATUS_ENDPOINT, fetcher);

  const rows = data?.items ?? [];

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <PageHeader
        title="Observability"
        description="Live service status, uptime against SLO, and error-budget burn across the fleet."
        actions={
          <Badge variant="info" className="gap-2">
            <span className="inline-flex size-1.5 animate-pulse-dot rounded-full bg-info" />
            {rows.length} service{rows.length === 1 ? "" : "s"} monitored
          </Badge>
        }
      />

      <StatusSummary rows={rows} loading={isLoading} />

      {isLoading ? (
        <GridSkeleton />
      ) : error ? (
        <EmptyState
          icon={<ShieldAlert />}
          title="Could not load status"
          description={error instanceof ApiError ? error.message : "Unexpected error."}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Radio />}
          title="No services registered"
          description="Register a service and attach health checks to start monitoring."
        />
      ) : (
        <StatusGrid rows={rows} canOperate={canOperate} onChecksRan={() => void mutate()} />
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Fleet summary stats
// --------------------------------------------------------------------------- //
function StatusSummary({ rows, loading }: { rows: StatusGridRow[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent>
              <Skeleton className="h-14 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const down = rows.filter((r) => r.status === "down").length;
  const openIncidents = rows.reduce((sum, r) => sum + r.open_incidents, 0);
  const breaching = rows.filter((r) => r.uptime_24h < r.slo_target).length;
  const avgUptime =
    rows.length > 0 ? rows.reduce((sum, r) => sum + r.uptime_24h, 0) / rows.length : 1;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent>
          <Stat
            label="Services up"
            value={`${rows.length - down}/${rows.length}`}
            tone={down > 0 ? "danger" : "ok"}
            icon={<SignalHigh />}
            sub={down > 0 ? `${down} down right now` : "All probes healthy"}
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Stat
            label="Avg uptime · 24h"
            value={formatPercent(avgUptime, 2)}
            tone={avgUptime >= 0.999 ? "ok" : avgUptime >= 0.99 ? "warn" : "danger"}
            icon={<Activity />}
            sub="Mean across monitored services"
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Stat
            label="SLO breaches · 24h"
            value={breaching}
            tone={breaching > 0 ? "warn" : "ok"}
            icon={<ShieldAlert />}
            sub={breaching > 0 ? "Below target uptime" : "Within budget"}
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Stat
            label="Open incidents"
            value={openIncidents}
            tone={openIncidents > 0 ? "danger" : "ok"}
            icon={<Radio />}
            sub={openIncidents > 0 ? "Active across services" : "No active incidents"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Expandable status grid
// --------------------------------------------------------------------------- //
interface StatusGridProps {
  rows: StatusGridRow[];
  canOperate: boolean;
  onChecksRan: () => void;
}

function StatusGrid({ rows, canOperate, onChecksRan }: StatusGridProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <Card className="overflow-hidden">
      <ul role="list" className="divide-y divide-border">
        {rows.map((row) => {
          const isOpen = expanded === row.service_id;
          return (
            <li key={row.service_id}>
              <ServiceRow
                row={row}
                open={isOpen}
                onToggle={() => setExpanded(isOpen ? null : row.service_id)}
              />
              {isOpen ? (
                <div className="bg-bg/60 noc-grid border-t border-border px-4 py-4 sm:px-6">
                  <ServiceDetail row={row} canOperate={canOperate} onChecksRan={onChecksRan} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

interface ServiceRowProps {
  row: StatusGridRow;
  open: boolean;
  onToggle: () => void;
}

function ServiceRow({ row, open, onToggle }: ServiceRowProps) {
  const meetsSlo = row.uptime_24h >= row.slo_target;
  const score = uptimeToScore(row.uptime_24h);

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={cn(
        "flex w-full items-center gap-4 px-4 py-3.5 text-left sm:px-6",
        "hover:bg-surface-2/50 transition-colors duration-[140ms]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent",
        open && "bg-surface-2/40",
      )}
    >
      <StatusDot status={row.status} pulse={row.status === "down"} />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-text">{row.service_name}</span>
          {row.open_incidents > 0 ? (
            <Badge variant="danger">
              {row.open_incidents} incident{row.open_incidents === 1 ? "" : "s"}
            </Badge>
          ) : null}
        </div>
        <span className="tabular text-xs text-text-dim">
          {row.check_count} check{row.check_count === 1 ? "" : "s"}
          {row.last_checked_at
            ? ` · checked ${formatRelative(row.last_checked_at)}`
            : " · never run"}
        </span>
      </div>

      <div className="hidden flex-col items-end sm:flex">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Uptime 24h
        </span>
        <span className={cn("tabular text-sm font-semibold", meetsSlo ? "text-ok" : "text-danger")}>
          {formatPercent(row.uptime_24h, 2)}
        </span>
      </div>

      <UptimeBar score={score} meetsSlo={meetsSlo} />

      <div className="flex flex-col items-end">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">SLO</span>
        <span className="tabular text-sm text-text-dim">{formatPercent(row.slo_target, 1)}</span>
      </div>

      <ChevronDown
        className={cn(
          "size-4 shrink-0 text-text-dim transition-transform duration-[180ms]",
          open && "rotate-180 text-text",
        )}
        aria-hidden="true"
      />
    </button>
  );
}

function UptimeBar({ score, meetsSlo }: { score: number; meetsSlo: boolean }) {
  return (
    <div
      className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-surface-2 md:block"
      aria-hidden="true"
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
          meetsSlo ? "bg-ok" : "bg-danger",
        )}
        style={{ width: `${Math.max(2, score)}%` }}
      />
    </div>
  );
}

function GridSkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="divide-y divide-border">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-6 py-4">
            <Skeleton className="size-2 rounded-full" />
            <Skeleton className="h-4 w-48" />
            <Skeleton className="ml-auto h-4 w-16" />
            <Skeleton className="h-1.5 w-24" />
          </div>
        ))}
      </div>
    </Card>
  );
}
