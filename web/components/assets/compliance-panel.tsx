"use client";

import { CheckCircle2, MinusCircle, ShieldCheck, XCircle } from "lucide-react";
import { useMemo } from "react";
import useSWR from "swr";

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  SeverityBadge,
  Skeleton,
} from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import type { ComplianceResult, ComplianceRule, ComplianceStatus, Page } from "@/lib/types";

export interface CompliancePanelProps {
  assetId: string;
}

const RESULT_LIMIT = 50;
const RULES_LIMIT = 200;

const STATUS_META: Record<
  ComplianceStatus,
  { label: string; tone: "ok" | "danger" | "default"; icon: typeof CheckCircle2 }
> = {
  pass: { label: "Pass", tone: "ok", icon: CheckCircle2 },
  fail: { label: "Fail", tone: "danger", icon: XCircle },
  not_applicable: { label: "N/A", tone: "default", icon: MinusCircle },
};

// Failing results first (highest signal for an operator), then by severity weight.
const SEVERITY_WEIGHT = { critical: 0, high: 1, medium: 2, low: 3 } as const;

export function CompliancePanel({ assetId }: CompliancePanelProps) {
  const { data, error, isLoading } = useSWR<Page<ComplianceResult>>(
    `/compliance/assets/${assetId}/results?limit=${RESULT_LIMIT}`,
    fetcher,
  );
  const { data: rulesPage } = useSWR<Page<ComplianceRule>>(
    `/compliance/rules?limit=${RULES_LIMIT}`,
    fetcher,
  );

  const ruleTitles = useMemo(() => {
    const map = new Map<string, string>();
    for (const rule of rulesPage?.items ?? []) map.set(rule.id, rule.title);
    return map;
  }, [rulesPage]);

  const results = useMemo(() => {
    const items = data?.items ?? [];
    return [...items].sort((a, b) => {
      const aFail = a.status === "fail" ? 0 : 1;
      const bFail = b.status === "fail" ? 0 : 1;
      if (aFail !== bFail) return aFail - bFail;
      return SEVERITY_WEIGHT[a.severity] - SEVERITY_WEIGHT[b.severity];
    });
  }, [data]);

  const failing = results.filter((r) => r.status === "fail").length;
  const passing = results.filter((r) => r.status === "pass").length;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <CardTitle>Compliance</CardTitle>
        {results.length > 0 ? (
          <div className="flex items-center gap-2">
            <Badge variant="ok">{passing} pass</Badge>
            <Badge variant={failing > 0 ? "danger" : "default"}>{failing} fail</Badge>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-danger">Couldn’t load compliance results.</p>
        ) : isLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : results.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck />}
            title="No compliance results"
            description="This asset hasn’t been evaluated in a compliance run yet."
          />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {results.map((result) => {
              const meta = STATUS_META[result.status];
              const Icon = meta.icon;
              return (
                <li key={result.id} className="flex items-center gap-3 py-2.5">
                  <Icon
                    className={
                      meta.tone === "ok"
                        ? "size-4 shrink-0 text-ok"
                        : meta.tone === "danger"
                          ? "size-4 shrink-0 text-danger"
                          : "size-4 shrink-0 text-muted"
                    }
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-text">
                      {ruleTitles.get(result.rule_id) ?? result.rule_id}
                    </p>
                    <p className="tabular text-[11px] text-text-dim">
                      {formatRelative(result.created_at)}
                    </p>
                  </div>
                  <SeverityBadge severity={result.severity} />
                  <Badge
                    variant={
                      meta.tone === "ok" ? "ok" : meta.tone === "danger" ? "danger" : "default"
                    }
                  >
                    {meta.label}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
