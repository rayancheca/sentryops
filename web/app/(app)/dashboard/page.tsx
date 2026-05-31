"use client";

// NOC overview — the operator console's hero screen. Pulls open incidents, MTTA
// / MTTR, compliance posture, the live service-status wall, and score drift in
// parallel via SWR, then lays them out bento-style with hierarchy by scale.

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Boxes,
  Clock,
  Gauge,
  ShieldCheck,
  Siren,
  Timer,
} from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  PageHeader,
  ScoreRing,
  SeverityBadge,
  Skeleton,
  Stat,
  StatusDot,
  type StatTone,
} from "@/components/ui";
import { ApiError, fetcher } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDuration, formatPercent, formatRelative, formatScore } from "@/lib/format";
import type { DriftPoint, Incident, MttaMttr, Page, StatusGridItem } from "@/lib/types";

import { DriftChart } from "./drift-chart";

// Mirrors backend app/schemas/compliance.py ScoreRead (not yet in lib/types).
interface ComplianceScore {
  run_id: string | null;
  org_score: number;
  total_assets: number;
  passed_count: number;
  failed_count: number;
  not_applicable_count: number;
  severity_failing: Record<string, number>;
  started_at: string | null;
}

const MTTR_WINDOW_HOURS = 720;
const SCORE_OK = 90;
const SCORE_WARN = 70;
const STATUS_REFRESH_MS = 30_000;

const SWR_OPTS = { revalidateOnFocus: false } as const;

function incidentTone(count: number): StatTone {
  if (count === 0) return "ok";
  if (count <= 2) return "warn";
  return "danger";
}

function scoreTone(score: number): StatTone {
  if (score >= SCORE_OK) return "ok";
  if (score >= SCORE_WARN) return "warn";
  return "danger";
}

function uptimeTone(uptime: number, slo: number): string {
  // uptime/slo arrive as fractions or percents; normalize to a 0..100 compare.
  const u = uptime <= 1 ? uptime * 100 : uptime;
  const target = slo <= 1 ? slo * 100 : slo;
  if (u >= target) return "text-ok";
  if (u >= target - 1) return "text-warn";
  return "text-danger";
}

export default function DashboardPage() {
  const incidents = useSWR<Page<Incident>>("/incidents?status=open&limit=8", fetcher, SWR_OPTS);
  const metrics = useSWR<MttaMttr>(
    `/incidents/metrics/mtta-mttr?window_hours=${MTTR_WINDOW_HOURS}`,
    fetcher,
    SWR_OPTS,
  );
  const score = useSWR<ComplianceScore>("/compliance/score", fetcher, SWR_OPTS);
  const drift = useSWR<Page<DriftPoint>>("/compliance/drift?limit=30", fetcher, SWR_OPTS);
  const status = useSWR<Page<StatusGridItem>>("/observability/status", fetcher, {
    ...SWR_OPTS,
    refreshInterval: STATUS_REFRESH_MS,
  });
  const assets = useSWR<Page<unknown>>("/assets?limit=1", fetcher, SWR_OPTS);

  const openCount = incidents.data?.total ?? 0;
  const servicesDown = status.data?.items.filter((s) => s.status === "down").length ?? 0;

  return (
    <>
      <PageHeader
        title="Operations Overview"
        description="Live posture across incidents, service health, and compliance."
        actions={
          <div className="flex items-center gap-4">
            <StatusDot
              status={servicesDown > 0 ? "down" : "up"}
              pulse
              label={servicesDown > 0 ? `${servicesDown} down` : "All systems"}
            />
            <span className="tabular hidden text-xs text-text-dim sm:inline">
              window {MTTR_WINDOW_HOURS / 24}d
            </span>
          </div>
        }
      />

      {/* Top metric row — hero numbers, hierarchy by scale + tone. */}
      <section aria-label="Key metrics" className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatPanel loading={incidents.isLoading} error={incidents.error}>
          <Stat
            label="Open Incidents"
            tone={incidentTone(openCount)}
            icon={<Siren />}
            value={openCount}
            sub={openCount === 0 ? "clear" : "needs attention"}
          />
        </StatPanel>

        <StatPanel loading={metrics.isLoading} error={metrics.error}>
          <Stat
            label="MTTR"
            icon={<Timer />}
            value={
              metrics.data?.mttr_seconds != null ? formatDuration(metrics.data.mttr_seconds) : "—"
            }
            sub="mean time to resolve"
          />
        </StatPanel>

        <StatPanel loading={metrics.isLoading} error={metrics.error}>
          <Stat
            label="MTTA"
            icon={<Clock />}
            value={
              metrics.data?.mtta_seconds != null ? formatDuration(metrics.data.mtta_seconds) : "—"
            }
            sub="mean time to ack"
          />
        </StatPanel>

        <StatPanel loading={score.isLoading} error={score.error}>
          <div className="flex items-center justify-between gap-2">
            <Stat
              label="Compliance"
              tone={score.data ? scoreTone(score.data.org_score) : "default"}
              icon={<ShieldCheck />}
              value={score.data ? formatScore(score.data.org_score) : "—"}
              sub={score.data ? `${score.data.failed_count} failing controls` : "no runs yet"}
            />
            {score.data ? <ScoreRing score={score.data.org_score} size={52} /> : null}
          </div>
        </StatPanel>

        <StatPanel loading={assets.isLoading} error={assets.error}>
          <Stat
            label="Total Assets"
            icon={<Boxes />}
            value={assets.data?.total ?? "—"}
            sub="tracked inventory"
          />
        </StatPanel>
      </section>

      {/* Mid band — status wall (wide) + drift chart. */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-accent" />
              Service Status
            </CardTitle>
            <Badge variant={servicesDown > 0 ? "danger" : "ok"}>
              {servicesDown > 0 ? `${servicesDown} DOWN` : `${status.data?.items.length ?? 0} UP`}
            </Badge>
          </CardHeader>
          <CardContent className="p-0">
            <ServiceStatusWall query={status} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Gauge className="size-4 text-accent" />
              Compliance Drift
            </CardTitle>
            {drift.data?.items.length ? (
              <span className="tabular text-xs text-text-dim">{drift.data.items.length} runs</span>
            ) : null}
          </CardHeader>
          <CardContent className="px-2 py-3">
            <DriftPanel query={drift} />
          </CardContent>
        </Card>
      </section>

      {/* Bottom — open incidents feed. */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-warn" />
            Open Incidents
          </CardTitle>
          <Link
            href="/incidents"
            className={cn(
              "tabular inline-flex items-center gap-1 text-xs font-medium text-text-dim",
              "rounded transition-colors hover:text-accent focus-visible:text-accent",
            )}
          >
            View all
            <ArrowRight className="size-3.5" />
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          <IncidentFeed query={incidents} />
        </CardContent>
      </Card>
    </>
  );
}

// ── Small composition helpers ─────────────────────────────────────────────

interface StatPanelProps {
  loading: boolean;
  error: unknown;
  children: React.ReactNode;
}

function StatPanel({ loading, error, children }: StatPanelProps) {
  return (
    <Card className="p-4 hover:border-accent-dim">
      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-7 w-16" />
          <Skeleton className="h-3 w-24" />
        </div>
      ) : error ? (
        <Stat
          label="Unavailable"
          tone="danger"
          icon={<AlertTriangle />}
          value="—"
          sub={error instanceof ApiError ? error.message : "load failed"}
        />
      ) : (
        children
      )}
    </Card>
  );
}

interface ServiceStatusWallProps {
  query: ReturnType<typeof useSWR<Page<StatusGridItem>>>;
}

function ServiceStatusWall({ query }: ServiceStatusWallProps) {
  if (query.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-px bg-border sm:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="bg-surface p-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="mt-2 h-3 w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (query.error) {
    return (
      <EmptyState
        className="border-danger/30 m-4"
        icon={<AlertTriangle className="text-danger" />}
        title="Status feed unavailable"
        description={query.error instanceof ApiError ? query.error.message : "Failed to load."}
      />
    );
  }

  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        className="m-4"
        icon={<Activity />}
        title="No services monitored"
        description="Add a service and health checks to populate the status wall."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-b-card bg-border sm:grid-cols-2">
      {items.map((svc) => (
        <div
          key={svc.service_id}
          className={cn(
            "group flex items-center justify-between gap-3 bg-surface px-4 py-3",
            "transition-colors hover:bg-surface-2",
          )}
        >
          <div className="flex min-w-0 items-center gap-3">
            <StatusDot status={svc.status} pulse={svc.status === "down"} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-text">{svc.service_name}</div>
              <div className="tabular text-xs text-text-dim">
                SLO {formatPercent(svc.slo_target)}
                {svc.open_incidents > 0 ? (
                  <span className="ml-2 text-danger">
                    {svc.open_incidents} incident{svc.open_incidents === 1 ? "" : "s"}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div
              className={cn(
                "tabular text-sm font-semibold",
                uptimeTone(svc.uptime_24h, svc.slo_target),
              )}
            >
              {formatPercent(svc.uptime_24h)}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-text-dim">24h uptime</div>
          </div>
        </div>
      ))}
    </div>
  );
}

interface DriftPanelProps {
  query: ReturnType<typeof useSWR<Page<DriftPoint>>>;
}

function DriftPanel({ query }: DriftPanelProps) {
  if (query.isLoading) {
    return <Skeleton className="h-44 w-full" />;
  }

  if (query.error) {
    return (
      <EmptyState
        icon={<AlertTriangle className="text-danger" />}
        title="Drift unavailable"
        description={query.error instanceof ApiError ? query.error.message : "Failed to load."}
      />
    );
  }

  const points = query.data?.items ?? [];
  if (points.length < 2) {
    return (
      <EmptyState
        icon={<Gauge />}
        title="Not enough history"
        description="Compliance drift appears after a few scan runs."
      />
    );
  }

  return (
    <div className="h-44 w-full">
      <DriftChart points={points} />
    </div>
  );
}

interface IncidentFeedProps {
  query: ReturnType<typeof useSWR<Page<Incident>>>;
}

function IncidentFeed({ query }: IncidentFeedProps) {
  if (query.isLoading) {
    return (
      <div className="divide-y divide-border">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-5 py-3">
            <Skeleton className="h-5 w-12" />
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    );
  }

  if (query.error) {
    return (
      <EmptyState
        className="border-danger/30 m-4"
        icon={<AlertTriangle className="text-danger" />}
        title="Incidents unavailable"
        description={query.error instanceof ApiError ? query.error.message : "Failed to load."}
      />
    );
  }

  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        className="m-4"
        icon={<ShieldCheck className="text-ok" />}
        title="No open incidents"
        description="Everything is operating within tolerance."
      />
    );
  }

  return (
    <ul className="divide-y divide-border">
      {items.map((inc) => (
        <li key={inc.id}>
          <Link
            href={`/incidents/${inc.id}`}
            className={cn(
              "group flex items-center gap-4 px-5 py-3 outline-none",
              "transition-colors hover:bg-surface-2 focus-visible:bg-surface-2",
            )}
          >
            <SeverityBadge severity={inc.severity} />
            <span className="min-w-0 flex-1 truncate text-sm text-text group-hover:text-text">
              {inc.title}
            </span>
            <StatusDot
              status={inc.status}
              pulse={inc.status === "open"}
              label={inc.status}
              className="hidden sm:inline-flex"
            />
            <span className="tabular w-20 shrink-0 text-right text-xs text-text-dim">
              {formatRelative(inc.opened_at)}
            </span>
            <ArrowRight className="size-4 shrink-0 text-text-dim opacity-0 transition-opacity group-hover:opacity-100" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
