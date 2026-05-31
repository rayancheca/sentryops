// Frontend-side typing for the compliance report payloads. The backend types
// `per_asset` and `failing_controls` as loosely-shaped dict/list bodies
// (see backend/app/schemas/compliance.py::ReportRead). We pin the exact shapes
// the service layer actually emits so the UI stays type-safe.

import type { Severity } from "@/lib/types";

/** One failing (asset, rule) row in the audit-ready report. */
export interface ReportFailingControl {
  asset_id: string;
  rule_id: string;
  title: string;
  framework: string;
  control: string;
  severity: Severity;
  remediation: string;
  evidence: Record<string, unknown>;
}

/** Per-asset rollup row in the audit-ready report. */
export interface ReportPerAsset {
  asset_id: string;
  score: number;
  passed: number;
  failed: number;
  not_applicable: number;
}

/** GET /compliance/report — audit-ready report for a single run. */
export interface ComplianceReport {
  run_id: string | null;
  generated_for: string;
  org_score: number;
  total_assets: number;
  status_counts: Record<string, number>;
  severity_failing: Record<string, number>;
  per_asset: ReportPerAsset[];
  failing_controls: ReportFailingControl[];
}

/** GET /compliance/score — org rollup for the latest run. */
export interface ComplianceScore {
  run_id: string | null;
  org_score: number;
  total_assets: number;
  passed_count: number;
  failed_count: number;
  not_applicable_count: number;
  severity_failing: Record<string, number>;
  started_at: string | null;
}

/** GET /compliance/newly-failing — a (rule, asset) pair newly failing. */
export interface NewlyFailingItem {
  asset_id: string;
  rule_id: string;
  severity: Severity;
  title: string;
  control: string;
}

// Severity ordering: critical first. Drives table sort + summary card order.
export const SEVERITY_ORDER: readonly Severity[] = ["critical", "high", "medium", "low"];

const SEVERITY_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** Anything sortable by severity then control reference. */
export interface SeverityControlSortable {
  severity: Severity;
  control: string;
  /** Stable tiebreak id — `rule_id` on results, `id` on catalogue rules. */
  rule_id?: string;
  id?: string;
}

/** Sort comparator: most severe first, then by control ref for stability. */
export function bySeverityThenControl(
  a: SeverityControlSortable,
  b: SeverityControlSortable,
): number {
  const rank = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
  if (rank !== 0) return rank;
  const control = a.control.localeCompare(b.control);
  if (control !== 0) return control;
  return (a.rule_id ?? a.id ?? "").localeCompare(b.rule_id ?? b.id ?? "");
}

/** Severity count for a card, reading the latest run's `severity_failing` map. */
export function failingForSeverity(
  map: Record<string, number> | undefined,
  severity: Severity,
): number {
  if (!map) return 0;
  return map[severity] ?? 0;
}
