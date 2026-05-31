// Frontend typing for observability payloads where the backend returns more
// than lib/types.ts pins. The shared `StatusGridItem` omits a few fields the
// status-grid endpoint actually emits (see backend/app/schemas/observability.py),
// and the uptime endpoint has no shared type, so we pin both here precisely.

import type { CheckStatus } from "@/lib/types";

/**
 * GET /observability/checks/{id}/run result. Mirrors CheckResultRead in
 * backend/app/schemas/observability.py; not pinned in lib/types.ts.
 */
export interface CheckResult {
  id: string;
  health_check_id: string;
  status: CheckStatus;
  latency_ms: number | null;
  status_code: number | null;
  error: string | null;
  created_at: string;
}

/** GET /observability/status — one row per service, as the API emits it. */
export interface StatusGridRow {
  service_id: string;
  service_name: string;
  asset_id: string | null;
  status: CheckStatus;
  uptime_24h: number;
  slo_target: number;
  check_count: number;
  open_incidents: number;
  last_checked_at: string | null;
  extra: Record<string, unknown> | null;
}

/** GET /observability/services/{id}/uptime?window_hours= */
export interface UptimeRead {
  window_hours: number;
  uptime: number;
  slo_target: number;
  error_budget: ErrorBudget;
}

/**
 * Error-budget rollup. The service computes a budget dict; we read the fields
 * we render (consumed fraction, remaining fraction, burn rate) defensively and
 * fall back when a key is absent.
 */
export interface ErrorBudget {
  allowed?: number;
  consumed?: number;
  remaining?: number;
  burn_rate?: number;
  [key: string]: number | undefined;
}

/** Selectable uptime windows for the per-service detail. */
export const UPTIME_WINDOWS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 24, label: "24h" },
  { value: 24 * 7, label: "7d" },
  { value: 24 * 30, label: "30d" },
];

/**
 * Uptime as a 0..100 score for ScoreRing / banding. The API returns a 0..1
 * fraction for `uptime` and `slo_target`.
 */
export function uptimeToScore(fraction: number): number {
  if (!Number.isFinite(fraction)) return 0;
  return Math.min(100, Math.max(0, fraction * 100));
}

/**
 * Error-budget burn as a 0..1 fraction of the allowed budget consumed.
 * Derives from observed uptime vs SLO target when the dict lacks a usable key:
 * burned = (target_downtime - actual_downtime is negative) → over budget.
 */
export function errorBudgetConsumed(budget: ErrorBudget, uptime: number, slo: number): number {
  if (typeof budget.consumed === "number" && Number.isFinite(budget.consumed)) {
    return clampFraction(budget.consumed);
  }
  const allowedDowntime = 1 - slo;
  if (allowedDowntime <= 0) return uptime >= 1 ? 0 : 1;
  const actualDowntime = 1 - uptime;
  return clampFraction(actualDowntime / allowedDowntime);
}

function clampFraction(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}
