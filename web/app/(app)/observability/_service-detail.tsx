"use client";

import { Gauge, Play, RefreshCw } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import {
  Badge,
  Button,
  EmptyState,
  Skeleton,
  Spinner,
  StatusDot,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { api, ApiError, fetcher } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatPercent } from "@/lib/format";
import type { HealthCheck, Page } from "@/lib/types";

import {
  errorBudgetConsumed,
  UPTIME_WINDOWS,
  uptimeToScore,
  type CheckResult,
  type StatusGridRow,
  type UptimeRead,
} from "./_types";

// Static class maps so Tailwind's JIT can see every tone variant.
const BURN_TEXT = { ok: "text-ok", warn: "text-warn", danger: "text-danger" } as const;
const BURN_BAR = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger" } as const;

interface ServiceDetailProps {
  row: StatusGridRow;
  canOperate: boolean;
  onChecksRan: () => void;
}

/**
 * Expanded view for one service: its health checks, and uptime across the
 * 24h / 7d / 30d windows with the error-budget burn for the selected window.
 */
export function ServiceDetail({ row, canOperate, onChecksRan }: ServiceDetailProps) {
  const [windowHours, setWindowHours] = useState<number>(UPTIME_WINDOWS[0]!.value);

  const checks = useSWR<Page<HealthCheck>>(
    `/observability/services/${row.service_id}/checks`,
    fetcher,
  );
  const uptime = useSWR<UptimeRead>(
    `/observability/services/${row.service_id}/uptime?window_hours=${windowHours}`,
    fetcher,
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_minmax(0,22rem)]">
      <ChecksList
        serviceId={row.service_id}
        query={checks}
        canOperate={canOperate}
        onChecksRan={() => {
          void checks.mutate();
          onChecksRan();
        }}
      />
      <UptimePanel
        windowHours={windowHours}
        onWindowChange={setWindowHours}
        query={uptime}
        sloTarget={row.slo_target}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Health checks list with per-check "run now"
// --------------------------------------------------------------------------- //
interface ChecksListProps {
  serviceId: string;
  query: ReturnType<typeof useSWR<Page<HealthCheck>>>;
  canOperate: boolean;
  onChecksRan: () => void;
}

function ChecksList({ query, canOperate, onChecksRan }: ChecksListProps) {
  const { data, error, isLoading } = query;

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-3/4" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-danger">
        {error instanceof ApiError ? error.message : "Failed to load health checks."}
      </p>
    );
  }

  const checks = data?.items ?? [];
  if (checks.length === 0) {
    return (
      <EmptyState title="No health checks" description="This service has no probes configured." />
    );
  }

  return (
    <div className="bg-bg/40 overflow-hidden rounded-card border border-border">
      <Table>
        <THead>
          <TR className="hover:bg-transparent">
            <TH>Check</TH>
            <TH className="w-px whitespace-nowrap">Type</TH>
            <TH>Target</TH>
            <TH className="w-px whitespace-nowrap text-right">Budget</TH>
            {canOperate ? <TH className="w-px" /> : null}
          </TR>
        </THead>
        <TBody>
          {checks.map((check) => (
            <CheckRow key={check.id} check={check} canOperate={canOperate} onRan={onChecksRan} />
          ))}
        </TBody>
      </Table>
    </div>
  );
}

interface CheckRowProps {
  check: HealthCheck;
  canOperate: boolean;
  onRan: () => void;
}

function CheckRow({ check, canOperate, onRan }: CheckRowProps) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  async function runNow() {
    setRunning(true);
    setRunError(null);
    try {
      const res = await api.post<CheckResult>(`/observability/checks/${check.id}/run`);
      setResult(res);
      onRan();
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Check failed to run.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <TR>
      <TD>
        <div className="flex items-center gap-2">
          <span className="font-medium text-text">{check.name}</span>
          {!check.enabled ? (
            <Badge variant="outline" className="uppercase">
              paused
            </Badge>
          ) : null}
          {result ? <StatusDot status={result.status} label={result.status} /> : null}
        </div>
        {result?.latency_ms != null ? (
          <span className="tabular text-xs text-text-dim">
            {Math.round(result.latency_ms)}ms
            {result.status_code != null ? ` · ${result.status_code}` : ""}
          </span>
        ) : null}
        {runError ? <span className="block text-xs text-danger">{runError}</span> : null}
      </TD>
      <TD className="text-text-dim">
        <Badge variant="default" className="uppercase">
          {check.check_type}
        </Badge>
      </TD>
      <TD>
        <span className="tabular truncate text-xs text-text-dim" title={check.target}>
          {check.method} {check.target}
          {check.port != null ? `:${check.port}` : ""}
        </span>
      </TD>
      <TD className="tabular text-right text-xs text-text-dim">{check.latency_budget_ms}ms</TD>
      {canOperate ? (
        <TD>
          <Button
            variant="ghost"
            size="sm"
            onClick={runNow}
            disabled={running || !check.enabled}
            aria-label={`Run ${check.name} now`}
          >
            {running ? <Spinner size={14} label="Running" /> : <Play />}
            <span className="sr-only sm:not-sr-only">Run</span>
          </Button>
        </TD>
      ) : null}
    </TR>
  );
}

// --------------------------------------------------------------------------- //
// Uptime + error-budget panel (window-switchable)
// --------------------------------------------------------------------------- //
interface UptimePanelProps {
  windowHours: number;
  onWindowChange: (hours: number) => void;
  query: ReturnType<typeof useSWR<UptimeRead>>;
  sloTarget: number;
}

function UptimePanel({ windowHours, onWindowChange, query, sloTarget }: UptimePanelProps) {
  const { data, error, isLoading } = query;

  return (
    <div className="bg-bg/40 flex flex-col gap-4 rounded-card border border-border p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-dim">
          <Gauge className="size-3.5" aria-hidden="true" /> Uptime
        </span>
        <div
          role="tablist"
          aria-label="Uptime window"
          className="inline-flex rounded-md border border-border bg-surface p-0.5"
        >
          {UPTIME_WINDOWS.map((w) => {
            const active = w.value === windowHours;
            return (
              <button
                key={w.value}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => onWindowChange(w.value)}
                className={cn(
                  "tabular rounded px-2.5 py-1 text-xs font-medium tracking-tight",
                  "transition-[color,background-color] duration-[140ms]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  active ? "bg-surface-2 text-text shadow-panel" : "text-text-dim hover:text-text",
                )}
              >
                {w.label}
              </button>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : error ? (
        <p className="text-sm text-danger">
          {error instanceof ApiError ? error.message : "Failed to load uptime."}
        </p>
      ) : data ? (
        <UptimeReadout data={data} sloTarget={sloTarget} />
      ) : null}
    </div>
  );
}

function UptimeReadout({ data, sloTarget }: { data: UptimeRead; sloTarget: number }) {
  const score = uptimeToScore(data.uptime);
  const meetsSlo = data.uptime >= data.slo_target;
  const consumed = errorBudgetConsumed(data.error_budget, data.uptime, data.slo_target);
  const burnTone = consumed >= 1 ? "danger" : consumed >= 0.75 ? "warn" : "ok";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <span
          className={cn(
            "tabular text-4xl font-semibold leading-none",
            meetsSlo ? "text-ok" : "text-danger",
          )}
        >
          {formatPercent(data.uptime, 3)}
        </span>
        <Badge variant={meetsSlo ? "ok" : "danger"}>SLO {formatPercent(sloTarget, 2)}</Badge>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium uppercase tracking-wider text-text-dim">
            Error budget burn
          </span>
          <span className={cn("tabular font-semibold", BURN_TEXT[burnTone])}>
            {formatPercent(consumed, 1)}
          </span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
          role="meter"
          aria-valuenow={Math.round(consumed * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Error budget consumed"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
              BURN_BAR[burnTone],
            )}
            style={{ width: `${Math.min(100, consumed * 100)}%` }}
          />
        </div>
        <span className="text-xs text-text-dim">
          {consumed >= 1
            ? "Budget exhausted for this window."
            : `${formatPercent(1 - consumed, 1)} remaining over ${formatWindow(data.window_hours)}.`}
        </span>
      </div>

      <span className="tabular flex items-center gap-1.5 text-[11px] text-muted">
        <RefreshCw className="size-3" aria-hidden="true" /> score {Math.round(score)} / 100
      </span>
    </div>
  );
}

function formatWindow(hours: number): string {
  if (hours <= 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}
