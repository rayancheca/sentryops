"use client";

import { History } from "lucide-react";
import useSWR from "swr";

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  type BadgeProps,
} from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDateTime, formatRelative } from "@/lib/format";

const AUDIT_LIMIT = 20;

// One audit row. Mirrors backend AuditRead (app/schemas/audit.py).
interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_id: string | null;
  source_ip: string | null;
  created_at: string;
}

interface AuditPage {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}

const ACTION_VARIANT: Record<string, NonNullable<BadgeProps["variant"]>> = {
  create: "ok",
  update: "info",
  delete: "danger",
  state_change: "warn",
  checkout: "warn",
  checkin: "info",
};

export interface AuditPanelProps {
  assetId: string;
}

export function AuditPanel({ assetId }: AuditPanelProps) {
  const { data, error, isLoading } = useSWR<AuditPage>(
    `/audit/asset/${assetId}?limit=${AUDIT_LIMIT}`,
    fetcher,
  );

  const items = data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit log</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-danger">Couldn’t load audit history.</p>
        ) : isLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<History />}
            title="No audit entries"
            description="Changes to this asset will appear here."
          />
        ) : (
          <ol className="relative flex flex-col">
            {items.map((entry, index) => (
              <li key={entry.id} className="flex gap-3 pb-4 last:pb-0">
                {/* Timeline rail */}
                <div className="flex flex-col items-center">
                  <span className="mt-1 size-2 shrink-0 rounded-full bg-accent-dim" />
                  {index < items.length - 1 ? (
                    <span className="mt-1 w-px flex-1 bg-border" aria-hidden="true" />
                  ) : null}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <Badge variant={ACTION_VARIANT[entry.action] ?? "default"}>
                      {entry.action.replace(/_/g, " ")}
                    </Badge>
                    <time
                      className="tabular text-[11px] text-text-dim"
                      dateTime={entry.created_at}
                      title={formatDateTime(entry.created_at)}
                    >
                      {formatRelative(entry.created_at)}
                    </time>
                  </div>
                  <p className="tabular truncate text-xs text-muted">
                    {entry.actor_id ? `actor ${entry.actor_id.slice(0, 8)}` : "system"}
                    {entry.source_ip ? ` · ${entry.source_ip}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
