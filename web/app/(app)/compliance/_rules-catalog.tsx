"use client";

import { BookText, ChevronDown } from "lucide-react";
import { useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  SeverityBadge,
  Skeleton,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import type { ComplianceRule } from "@/lib/types";

import { bySeverityThenControl } from "./_types";

export interface RulesCatalogProps {
  rules: ComplianceRule[] | undefined;
  isLoading: boolean;
}

export function RulesCatalog({ rules, isLoading }: RulesCatalogProps) {
  const [open, setOpen] = useState(false);
  const count = rules?.length ?? 0;
  const sorted = rules ? [...rules].sort(bySeverityThenControl) : [];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="p-0">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex w-full items-center justify-between gap-3 px-5 py-4 text-left",
            "hover:bg-surface-2/50 transition-colors duration-[140ms]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent",
          )}
        >
          <span className="flex items-center gap-2">
            <BookText className="size-4 text-text-dim" aria-hidden="true" />
            <CardTitle className="border-0 p-0">Control catalogue</CardTitle>
            <span className="tabular rounded bg-surface-2 px-1.5 py-0.5 text-xs text-text-dim">
              {isLoading ? "…" : count}
            </span>
          </span>
          <ChevronDown
            className={cn(
              "size-4 text-text-dim transition-transform duration-[200ms]",
              open && "rotate-180",
            )}
            aria-hidden="true"
          />
        </button>
      </CardHeader>

      {open ? (
        <CardContent className="animate-fade-in p-0">
          {isLoading ? (
            <div className="flex flex-col gap-2 px-5 py-4">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-5 w-3/4" />
            </div>
          ) : count === 0 ? (
            <div className="flex items-center gap-2 px-5 py-6 text-sm text-text-dim">
              <Spinner size={16} /> No rules registered.
            </div>
          ) : (
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH className="w-[44%]">Rule</TH>
                  <TH className="w-[12%]">Severity</TH>
                  <TH>Description</TH>
                </TR>
              </THead>
              <TBody>
                {sorted.map((rule) => (
                  <TR key={rule.id} className="align-top">
                    <TD className="align-top">
                      <div className="font-medium text-text">{rule.title}</div>
                      <div className="tabular mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-text-dim">
                        <span className="rounded bg-surface-2 px-1.5 py-0.5 uppercase tracking-wide">
                          {rule.framework}
                        </span>
                        <span>{rule.control}</span>
                      </div>
                    </TD>
                    <TD className="align-top">
                      <SeverityBadge severity={rule.severity} />
                    </TD>
                    <TD className="align-top">
                      <span className="text-sm text-text-dim">{rule.description}</span>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      ) : null}
    </Card>
  );
}
