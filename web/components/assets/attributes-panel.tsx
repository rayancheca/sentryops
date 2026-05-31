"use client";

import { Card, CardContent, CardHeader, CardTitle, Badge } from "@/components/ui";
import type { Asset } from "@/lib/types";

export interface AttributesPanelProps {
  asset: Asset;
}

// Humanize a snake_case attribute key into "Title Case".
function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bOs\b/, "OS")
    .replace(/\bEol\b/, "EOL")
    .replace(/\bEdr\b/, "EDR")
    .replace(/\bTls\b/, "TLS")
    .replace(/\bIp\b/, "IP");
}

// Render a single attribute value with a tone hint for booleans (security posture).
function ValueCell({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted">—</span>;
  }
  if (typeof value === "boolean") {
    return <Badge variant={value ? "ok" : "danger"}>{value ? "Yes" : "No"}</Badge>;
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? (
      <span className="text-muted">—</span>
    ) : (
      <span className="tabular text-text">{value.join(", ")}</span>
    );
  }
  if (typeof value === "object") {
    return <span className="tabular text-xs text-text-dim">{JSON.stringify(value)}</span>;
  }
  return <span className="tabular text-text">{String(value)}</span>;
}

export function AttributesPanel({ asset }: AttributesPanelProps) {
  const entries = Object.entries(asset.attributes ?? {}).filter(
    ([, v]) => v !== null && v !== undefined,
  );
  const customEntries = Object.entries(asset.custom_fields ?? {});

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attributes</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {entries.length === 0 ? (
          <p className="text-sm text-text-dim">No security-posture attributes recorded.</p>
        ) : (
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
            {entries.map(([key, value]) => (
              <div
                key={key}
                className="border-border/60 flex items-center justify-between gap-4 border-b pb-2"
              >
                <dt className="text-xs uppercase tracking-wide text-text-dim">{humanize(key)}</dt>
                <dd className="text-right text-sm">
                  <ValueCell value={value} />
                </dd>
              </div>
            ))}
          </dl>
        )}

        {customEntries.length > 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-text-dim">
              Custom fields
            </p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              {customEntries.map(([key, value]) => (
                <div
                  key={key}
                  className="border-border/60 flex items-center justify-between gap-4 border-b pb-2"
                >
                  <dt className="text-xs uppercase tracking-wide text-text-dim">{humanize(key)}</dt>
                  <dd className="text-right text-sm">
                    <ValueCell value={value} />
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
