"use client";

// Compliance org-score drift over recent runs. A calm area sparkline themed on
// the semantic palette: the fill band telegraphs the score, the baseline marks
// the 90 "ok" floor so a reviewer reads health at a glance.

import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { formatDateTime, formatScore } from "@/lib/format";
import type { DriftPoint } from "@/lib/types";

const OK_BAND = 90;
const WARN_BAND = 70;

// Color the series by the latest score's band so the chart stays semantic, not
// decorative. Matches ScoreRing's >=90 ok, >=70 warn, else danger.
function bandColor(score: number): string {
  if (score >= OK_BAND) return "var(--color-ok)";
  if (score >= WARN_BAND) return "var(--color-warn)";
  return "var(--color-danger)";
}

interface ChartDatum {
  ts: number;
  label: string;
  score: number;
}

function DriftTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload as ChartDatum | undefined;
  if (!datum) return null;

  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2 shadow-panel">
      <div className="tabular text-lg font-semibold leading-none text-text">
        {formatScore(datum.score)}
        <span className="ml-1 text-xs font-normal text-text-dim">/ 100</span>
      </div>
      <div className="tabular mt-1 text-[11px] text-text-dim">{datum.label}</div>
    </div>
  );
}

export interface DriftChartProps {
  points: DriftPoint[];
}

export function DriftChart({ points }: DriftChartProps) {
  // Drift comes newest-first from the API; chart left-to-right oldest-first.
  const data: ChartDatum[] = [...points]
    .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))
    .map((p) => ({
      ts: Date.parse(p.started_at),
      label: formatDateTime(p.started_at),
      score: p.org_score,
    }));

  const latest = data.at(-1)?.score ?? 100;
  const stroke = bandColor(latest);
  const gradientId = "drift-fill";

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        <ReferenceLine
          y={OK_BAND}
          stroke="var(--color-border)"
          strokeDasharray="3 4"
          ifOverflow="extendDomain"
        />

        <XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} hide scale="time" />
        <YAxis
          domain={[0, 100]}
          width={36}
          tick={{ fill: "var(--color-text-dim)", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          ticks={[0, 50, 100]}
        />
        <Tooltip content={<DriftTooltip />} cursor={{ stroke: "var(--color-muted)" }} />

        <Area
          type="monotone"
          dataKey="score"
          stroke={stroke}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{ r: 3, fill: stroke, stroke: "var(--color-bg)", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
