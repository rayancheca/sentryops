"use client";

import { ShieldCheck } from "lucide-react";

import { EmptyState, SeverityBadge, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

import { bySeverityThenControl, type ReportFailingControl } from "./_types";

export interface FailingTableProps {
  controls: ReportFailingControl[];
  /** asset_id -> display name (short_code · name), built from GET /assets. */
  assetNames: Map<string, string>;
}

export function FailingTable({ controls, assetNames }: FailingTableProps) {
  if (controls.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck />}
        title="No failing controls"
        description="Every in-scope asset passed every control in the latest evaluation."
      />
    );
  }

  const sorted = [...controls].sort(bySeverityThenControl);

  return (
    <Table>
      <THead sticky>
        <TR className="hover:bg-transparent">
          <TH className="w-[42%]">Control</TH>
          <TH className="w-[14%]">Severity</TH>
          <TH className="w-[20%]">Affected asset</TH>
          <TH className="w-[24%]">Remediation</TH>
        </TR>
      </THead>
      <TBody>
        {sorted.map((c) => {
          const assetLabel = assetNames.get(c.asset_id);
          return (
            <TR key={`${c.asset_id}:${c.rule_id}`} className="align-top">
              <TD className="align-top">
                <div className="font-medium text-text">{c.title}</div>
                <div className="tabular mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-text-dim">
                  <span className="rounded bg-surface-2 px-1.5 py-0.5 uppercase tracking-wide">
                    {c.framework || "—"}
                  </span>
                  <span>{c.control || c.rule_id}</span>
                </div>
              </TD>
              <TD className="align-top">
                <SeverityBadge severity={c.severity} />
              </TD>
              <TD className="align-top">
                {assetLabel ? (
                  <span className="tabular text-sm text-text">{assetLabel}</span>
                ) : (
                  <span className="tabular text-xs text-text-dim" title={c.asset_id}>
                    {c.asset_id.slice(0, 8)}…
                  </span>
                )}
              </TD>
              <TD className="align-top">
                <span className="text-sm text-text-dim">{c.remediation || "—"}</span>
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
