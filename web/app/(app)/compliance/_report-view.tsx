"use client";

import { FileText, Printer } from "lucide-react";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ScoreRing,
  SeverityBadge,
  Stat,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { formatDateTime, formatScore } from "@/lib/format";

import { FailingTable } from "./_failing-table";
import { SEVERITY_ORDER, type ComplianceReport, type ReportPerAsset } from "./_types";

function scoreTone(score: number): "ok" | "warn" | "danger" {
  if (score >= 90) return "ok";
  if (score >= 70) return "warn";
  return "danger";
}

interface PerAssetTableProps {
  rows: ReportPerAsset[];
  assetNames: Map<string, string>;
}

function PerAssetTable({ rows, assetNames }: PerAssetTableProps) {
  return (
    <Table>
      <THead sticky>
        <TR className="hover:bg-transparent">
          <TH>Asset</TH>
          <TH className="w-24 text-right">Score</TH>
          <TH className="w-20 text-right">Pass</TH>
          <TH className="w-20 text-right">Fail</TH>
          <TH className="w-20 text-right">N/A</TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((row) => {
          const label = assetNames.get(row.asset_id) ?? `${row.asset_id.slice(0, 8)}…`;
          const tone = scoreTone(row.score);
          const toneClass =
            tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-danger";
          return (
            <TR key={row.asset_id}>
              <TD className="tabular text-sm">{label}</TD>
              <TD className={`tabular text-right font-semibold ${toneClass}`}>
                {formatScore(row.score)}
              </TD>
              <TD className="tabular text-right text-ok">{row.passed}</TD>
              <TD className="tabular text-right text-danger">{row.failed}</TD>
              <TD className="tabular text-right text-text-dim">{row.not_applicable}</TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

export interface ReportViewProps {
  report: ComplianceReport;
  assetNames: Map<string, string>;
}

export function ReportView({ report, assetNames }: ReportViewProps) {
  if (!report.run_id) {
    return (
      <EmptyState
        icon={<FileText />}
        title="No report available"
        description="Run an evaluation to generate the first audit-ready compliance report."
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle className="border-0 p-0">Audit-ready report</CardTitle>
            <span className="tabular text-xs text-text-dim">
              Generated {formatDateTime(report.generated_for)} · run {report.run_id.slice(0, 8)}
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer aria-hidden="true" />
            Export / print
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            <div className="flex items-center gap-4">
              <ScoreRing score={report.org_score} size={92} />
              <Stat
                label="Org score"
                value={formatScore(report.org_score)}
                sub={`${report.total_assets} assets in scope`}
                tone={scoreTone(report.org_score)}
              />
            </div>
            <div className="grid flex-1 grid-cols-3 gap-4 border-t border-border pt-4 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
              <Stat label="Passed" value={report.status_counts.pass ?? 0} tone="ok" />
              <Stat label="Failed" value={report.status_counts.fail ?? 0} tone="danger" />
              <Stat label="N/A" value={report.status_counts.not_applicable ?? 0} tone="default" />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
            <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
              Failing by severity
            </span>
            {SEVERITY_ORDER.map((sev) => (
              <span key={sev} className="inline-flex items-center gap-1.5">
                <SeverityBadge severity={sev} />
                <span className="tabular text-sm text-text">
                  {report.severity_failing[sev] ?? 0}
                </span>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Failing controls ({report.failing_controls.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <FailingTable controls={report.failing_controls} assetNames={assetNames} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Per-asset breakdown ({report.per_asset.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {report.per_asset.length === 0 ? (
            <EmptyState title="No assets evaluated" className="m-5" />
          ) : (
            <PerAssetTable rows={report.per_asset} assetNames={assetNames} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
