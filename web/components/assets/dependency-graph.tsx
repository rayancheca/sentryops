"use client";

import Link from "next/link";
import { useId, useMemo } from "react";

import { ASSET_TYPE_LABEL } from "@/lib/asset-labels";
import { cn } from "@/lib/cn";
import type { DependencyNode, DependencyTree } from "@/lib/types";

export interface DependencyGraphProps {
  /** Tree of assets this asset depends on (transitive). */
  upstream?: DependencyTree | null;
  /** Tree of assets that depend on this asset (transitive). */
  downstream?: DependencyTree | null;
  className?: string;
}

interface Column {
  side: "upstream" | "downstream";
  label: string;
  nodes: DependencyNode[];
}

// Build the direct-neighbour set for one side. Trees come back rooted at the
// focused asset; we surface its immediate neighbours as the first ring and keep
// any deeper transitive nodes as a flat, de-duplicated, cycle-safe list.
function neighboursFor(tree: DependencyTree | null | undefined): DependencyNode[] {
  if (!tree) return [];
  const rootId = tree.asset.id;
  const byId = new Map<string, DependencyNode>();
  for (const node of tree.nodes) {
    if (node.id !== rootId) byId.set(node.id, node);
  }
  // Stable order: edges define adjacency; iterate edges first, then any orphans.
  const ordered: DependencyNode[] = [];
  const seen = new Set<string>();
  for (const edge of tree.edges) {
    for (const id of [edge.source_asset_id, edge.target_asset_id]) {
      if (id === rootId || seen.has(id)) continue;
      const node = byId.get(id);
      if (node) {
        seen.add(id);
        ordered.push(node);
      }
    }
  }
  for (const [id, node] of byId) {
    if (!seen.has(id)) ordered.push(node);
  }
  return ordered;
}

function NodeChip({ node, dim = false }: { node: DependencyNode; dim?: boolean }) {
  return (
    <Link
      href={`/assets/${node.id}`}
      className={cn(
        "group/node block rounded-md border border-border bg-surface px-3 py-2",
        "transition-[transform,border-color,background-color] duration-[140ms]",
        "hover:-translate-y-px hover:border-accent-dim hover:bg-surface-2",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        dim && "opacity-90",
      )}
    >
      <div className="truncate text-sm font-medium text-text group-hover/node:text-text">
        {node.name}
      </div>
      <div className="tabular mt-0.5 text-[11px] uppercase tracking-wide text-text-dim">
        {ASSET_TYPE_LABEL[node.asset_type] ?? node.asset_type}
      </div>
    </Link>
  );
}

function FocusChip({ node }: { node: DependencyNode }) {
  return (
    <div className="rounded-md border border-accent-dim bg-surface-2 px-3 py-2 shadow-glow">
      <div className="truncate text-sm font-semibold text-text">{node.name}</div>
      <div className="tabular mt-0.5 text-[11px] uppercase tracking-wide text-accent">
        {ASSET_TYPE_LABEL[node.asset_type] ?? node.asset_type} · this asset
      </div>
    </div>
  );
}

function SideColumn({ column }: { column: Column }) {
  const isUpstream = column.side === "upstream";
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div
        className={cn(
          "text-[11px] font-semibold uppercase tracking-wider text-text-dim",
          isUpstream ? "text-left" : "text-right",
        )}
      >
        {column.label}
        <span className="tabular ml-1.5 text-muted">({column.nodes.length})</span>
      </div>
      {column.nodes.length === 0 ? (
        <div
          className={cn(
            "bg-surface/40 rounded-md border border-dashed border-border px-3 py-2",
            "text-xs text-muted",
          )}
        >
          {isUpstream ? "No upstream dependencies" : "No dependents"}
        </div>
      ) : (
        column.nodes.map((node) => <NodeChip key={`${column.side}-${node.id}`} node={node} dim />)
      )}
    </div>
  );
}

export function DependencyGraph({ upstream, downstream, className }: DependencyGraphProps) {
  const gradientId = useId();
  const focus = upstream?.asset ?? downstream?.asset ?? null;

  const upstreamNodes = useMemo(() => neighboursFor(upstream), [upstream]);
  const downstreamNodes = useMemo(() => neighboursFor(downstream), [downstream]);

  if (!focus) return null;

  const hasUp = upstreamNodes.length > 0;
  const hasDown = downstreamNodes.length > 0;

  return (
    <div className={cn("relative", className)}>
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[1fr_auto_1fr]">
        <SideColumn column={{ side: "upstream", label: "Upstream", nodes: upstreamNodes }} />

        {/* Center column: connectors + the focused asset. */}
        <div className="flex flex-col items-stretch gap-3 md:px-6">
          <div className="text-center text-[11px] font-semibold uppercase tracking-wider text-text-dim">
            Focus
          </div>
          <div className="relative">
            {/* Connector lines — purely decorative, hidden on stacked mobile. */}
            <svg
              className="pointer-events-none absolute inset-0 hidden h-full w-full md:block"
              aria-hidden="true"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient id={`${gradientId}-l`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="var(--color-border)" stopOpacity="0" />
                  <stop offset="100%" stopColor="var(--color-accent-dim)" stopOpacity="0.9" />
                </linearGradient>
                <linearGradient id={`${gradientId}-r`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="var(--color-accent-dim)" stopOpacity="0.9" />
                  <stop offset="100%" stopColor="var(--color-border)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {hasUp ? (
                <line
                  x1="-24"
                  y1="50%"
                  x2="50%"
                  y2="50%"
                  stroke={`url(#${gradientId}-l)`}
                  strokeWidth="1.5"
                />
              ) : null}
              {hasDown ? (
                <line
                  x1="50%"
                  y1="50%"
                  x2="calc(100% + 24px)"
                  y2="50%"
                  stroke={`url(#${gradientId}-r)`}
                  strokeWidth="1.5"
                />
              ) : null}
            </svg>
            <FocusChip node={focus} />
          </div>
        </div>

        <SideColumn column={{ side: "downstream", label: "Downstream", nodes: downstreamNodes }} />
      </div>
    </div>
  );
}
