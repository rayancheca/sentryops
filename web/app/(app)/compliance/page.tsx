"use client";

import { AlertTriangle, Play, ShieldAlert, ShieldCheck, TrendingUp } from "lucide-react";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  PageHeader,
  ScoreRing,
  SeverityBadge,
  Skeleton,
  Spinner,
  Stat,
  Tabs,
  type TabItem,
} from "@/components/ui";
import { ApiError, api, fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatScore } from "@/lib/format";
import type {
  AssetListItem,
  ComplianceRule,
  ComplianceRun,
  DriftPoint,
  Page,
  Severity,
} from "@/lib/types";

import { DriftChart } from "./_drift-chart";
import { FailingTable } from "./_failing-table";
import { ReportView } from "./_report-view";
import { RulesCatalog } from "./_rules-catalog";
import {
  SEVERITY_ORDER,
  failingForSeverity,
  type ComplianceReport,
  type ComplianceScore,
  type NewlyFailingItem,
} from "./_types";

// Endpoints used by this surface; kept together so mutate() targets stay exact.
const SCORE_KEY = "/compliance/score";
const DRIFT_KEY = "/compliance/drift?limit=30";
const NEWLY_KEY = "/compliance/newly-failing";
const REPORT_KEY = "/compliance/report";
const RULES_KEY = "/compliance/rules";
const ASSETS_KEY = "/assets?limit=500";

const SEVERITY_TONE: Record<Severity, "danger" | "warn"> = {
  critical: "danger",
  high: "danger",
  medium: "warn",
  low: "warn",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

type ViewTab = "posture" | "report";

const TABS: ReadonlyArray<TabItem<ViewTab>> = [
  { value: "posture", label: "Posture" },
  { value: "report", label: "Audit report" },
];

function scoreTone(score: number): "ok" | "warn" | "danger" {
  if (score >= 90) return "ok";
  if (score >= 70) return "warn";
  return "danger";
}

// Explicit, static class names so Tailwind's JIT scanner keeps them.
const SCORE_TONE_TEXT: Record<"ok" | "warn" | "danger", string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
};

function buildAssetNames(assets: AssetListItem[] | undefined): Map<string, string> {
  const map = new Map<string, string>();
  for (const a of assets ?? []) map.set(a.id, `${a.short_code} · ${a.name}`);
  return map;
}

export default function CompliancePage() {
  const { hasRole } = useAuth();
  const { mutate } = useSWRConfig();
  const canRun = hasRole("operator");

  const [tab, setTab] = useState<ViewTab>("posture");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const score = useSWR<ComplianceScore>(SCORE_KEY, fetcher);
  const drift = useSWR<Page<DriftPoint>>(DRIFT_KEY, fetcher);
  const newly = useSWR<Page<NewlyFailingItem>>(NEWLY_KEY, fetcher);
  const report = useSWR<ComplianceReport>(REPORT_KEY, fetcher);
  const rules = useSWR<Page<ComplianceRule>>(RULES_KEY, fetcher);
  const assets = useSWR<Page<AssetListItem>>(ASSETS_KEY, fetcher);

  const assetNames = buildAssetNames(assets.data?.items);
  const latest = score.data;
  const hasRun = Boolean(latest?.run_id);

  async function handleRun() {
    setRunError(null);
    setRunning(true);
    try {
      await api.post<ComplianceRun>("/compliance/runs");
      // Revalidate every dependent view after a fresh evaluation.
      await Promise.all([
        mutate(SCORE_KEY),
        mutate(DRIFT_KEY),
        mutate(NEWLY_KEY),
        mutate(REPORT_KEY),
      ]);
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Evaluation failed. Try again.");
    } finally {
      setRunning(false);
    }
  }

  const anyError = score.error ?? report.error;

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <PageHeader
        title="Compliance posture"
        description="Continuous control evaluation across in-scope assets — org score, drift, and audit-ready evidence."
        actions={
          canRun ? (
            <Button onClick={handleRun} disabled={running}>
              {running ? (
                <Spinner size={16} label="Running evaluation" />
              ) : (
                <Play aria-hidden="true" />
              )}
              {running ? "Evaluating…" : "Run evaluation"}
            </Button>
          ) : (
            <Badge variant="outline" title="Operator role required to trigger runs">
              Read-only
            </Badge>
          )
        }
      />

      {runError ? (
        <Card className="border-danger/40">
          <CardContent className="flex items-center gap-2 py-3 text-sm text-danger">
            <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
            {runError}
          </CardContent>
        </Card>
      ) : null}

      {anyError instanceof ApiError ? (
        <Card className="border-danger/40">
          <CardContent className="flex items-center gap-2 py-3 text-sm text-danger">
            <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
            {anyError.message}
          </CardContent>
        </Card>
      ) : null}

      {/* Header summary: big score ring + failing-by-severity stat cards. */}
      <section aria-label="Compliance summary" className="grid gap-4 lg:grid-cols-[auto_1fr]">
        <Card className="noc-grid">
          <CardContent className="flex items-center gap-5">
            {score.isLoading ? (
              <Skeleton className="size-28 rounded-full" />
            ) : (
              <ScoreRing score={latest?.org_score ?? 100} size={112} />
            )}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
                Org score
              </span>
              <span
                className={`tabular text-4xl font-semibold leading-none ${
                  SCORE_TONE_TEXT[scoreTone(latest?.org_score ?? 100)]
                }`}
              >
                {latest ? formatScore(latest.org_score) : "—"}
              </span>
              <span className="tabular mt-1 text-xs text-text-dim">
                {hasRun && latest?.started_at
                  ? `Last run ${formatDateTime(latest.started_at)}`
                  : "Awaiting first evaluation"}
              </span>
              <span className="tabular text-xs text-text-dim">
                {latest ? `${latest.total_assets} assets · ${latest.failed_count} failures` : ""}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Failing controls by severity</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {SEVERITY_ORDER.map((sev) => {
              const count = failingForSeverity(latest?.severity_failing, sev);
              return (
                <Stat
                  key={sev}
                  label={SEVERITY_LABEL[sev]}
                  value={score.isLoading ? "—" : count}
                  tone={count > 0 ? SEVERITY_TONE[sev] : "default"}
                  icon={count > 0 ? <ShieldAlert /> : <ShieldCheck />}
                />
              );
            })}
          </CardContent>
        </Card>
      </section>

      {/* Drift: the compliance-over-time story. */}
      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <TrendingUp className="size-4 text-accent" aria-hidden="true" />
          <CardTitle className="border-0 p-0">Compliance drift</CardTitle>
        </CardHeader>
        <CardContent>
          {drift.isLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : (drift.data?.items.length ?? 0) < 2 ? (
            <EmptyState
              icon={<TrendingUp />}
              title="Not enough history yet"
              description="Drift appears once at least two evaluations have been recorded."
            />
          ) : (
            <DriftChart points={drift.data!.items} />
          )}
        </CardContent>
      </Card>

      {/* Newly failing since last run — highlighted regression callout. */}
      <NewlyFailing items={newly.data?.items} isLoading={newly.isLoading} assetNames={assetNames} />

      {/* Posture / report views. */}
      <div className="flex items-center justify-between">
        <Tabs<ViewTab> tabs={TABS} value={tab} onValueChange={setTab} />
        {report.data?.run_id ? (
          <span className="tabular text-xs text-text-dim">
            Run {report.data.run_id.slice(0, 8)}
          </span>
        ) : null}
      </div>

      {tab === "posture" ? (
        <Card>
          <CardHeader>
            <CardTitle>Failing controls ({report.data?.failing_controls.length ?? 0})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {report.isLoading ? (
              <div className="flex flex-col gap-2 p-5">
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-6 w-1/2" />
              </div>
            ) : report.data ? (
              <FailingTable controls={report.data.failing_controls} assetNames={assetNames} />
            ) : (
              <EmptyState title="No data" className="m-5" />
            )}
          </CardContent>
        </Card>
      ) : report.isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : report.data ? (
        <ReportView report={report.data} assetNames={assetNames} />
      ) : (
        <EmptyState title="No report available" />
      )}

      {/* Secondary panel: the static control catalogue. */}
      <RulesCatalog rules={rules.data?.items} isLoading={rules.isLoading} />
    </div>
  );
}

interface NewlyFailingProps {
  items: NewlyFailingItem[] | undefined;
  isLoading: boolean;
  assetNames: Map<string, string>;
}

function NewlyFailing({ items, isLoading, assetNames }: NewlyFailingProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Newly failing since last run</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-6 w-1/3" />
        </CardContent>
      </Card>
    );
  }

  const list = items ?? [];
  const hasRegressions = list.length > 0;

  return (
    <Card className={hasRegressions ? "border-warn/40 shadow-glow" : undefined}>
      <CardHeader className="flex-row items-center gap-2">
        <AlertTriangle
          className={`size-4 ${hasRegressions ? "text-warn" : "text-text-dim"}`}
          aria-hidden="true"
        />
        <CardTitle className="border-0 p-0">Newly failing since last run</CardTitle>
        {hasRegressions ? (
          <Badge variant="warn" className="ml-1">
            {list.length}
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className={hasRegressions ? "flex flex-col gap-2" : "p-0"}>
        {!hasRegressions ? (
          <EmptyState
            icon={<ShieldCheck />}
            title="No regressions"
            description="No control started failing between the previous run and the latest one."
            className="border-0 bg-transparent"
          />
        ) : (
          list.map((item) => {
            const assetLabel = assetNames.get(item.asset_id) ?? `${item.asset_id.slice(0, 8)}…`;
            return (
              <div
                key={`${item.asset_id}:${item.rule_id}`}
                className="bg-surface-2/40 flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
              >
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium text-text">{item.title}</span>
                  <span className="tabular text-xs text-text-dim">
                    {item.control} · {assetLabel}
                  </span>
                </div>
                <SeverityBadge severity={item.severity} />
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
