"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDateTime, formatRelative, formatScore } from "@/lib/format";
import type { DriftPoint } from "@/lib/types";

// SLO-like posture band. >=90 is the "healthy compliance" floor we hold the
// org to; below 70 is the danger zone. These mirror the ScoreRing bands.
const SLO_FLOOR = 90;
const DANGER_FLOOR = 70;

interface DriftDatum {
  ts: number;
  score: number;
  label: string;
  iso: string;
}

function toData(points: DriftPoint[]): DriftDatum[] {
  return points.map((p) => ({
    ts: Date.parse(p.started_at),
    score: Math.round(p.org_score),
    label: formatRelative(p.started_at),
    iso: p.started_at,
  }));
}

interface DriftTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: DriftDatum }>;
}

function DriftTooltip({ active, payload }: DriftTooltipProps) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload;
  if (!datum) return null;
  const tone =
    datum.score >= SLO_FLOOR
      ? "text-ok"
      : datum.score >= DANGER_FLOOR
        ? "text-warn"
        : "text-danger";
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2 shadow-panel">
      <div className="tabular text-xs text-text-dim">{formatDateTime(datum.iso)}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`tabular text-lg font-semibold leading-none ${tone}`}>{datum.score}</span>
        <span className="text-xs text-text-dim">org score</span>
      </div>
    </div>
  );
}

export interface DriftChartProps {
  points: DriftPoint[];
}

export function DriftChart({ points }: DriftChartProps) {
  const data = toData(points);
  const latest = data[data.length - 1];
  const first = data[0];

  return (
    <div>
      <div className="flex items-end justify-between px-1 pb-3">
        <div className="flex flex-col">
          <span className="text-xs font-medium uppercase tracking-wider text-text-dim">
            Org score over time
          </span>
          <span className="tabular mt-1 text-2xl font-semibold leading-none text-text">
            {latest ? formatScore(latest.score) : "—"}
            <span className="ml-2 text-sm font-normal text-text-dim">/ 100</span>
          </span>
        </div>
        {first && latest ? (
          <span className="tabular text-xs text-text-dim">
            {data.length} runs · {first.label} → {latest.label}
          </span>
        ) : null}
      </div>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
            <defs>
              <linearGradient id="driftFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0.02} />
              </linearGradient>
            </defs>

            {/* SLO posture band: healthy floor (>=90) shaded ok. */}
            <ReferenceArea
              y1={SLO_FLOOR}
              y2={100}
              fill="var(--color-ok)"
              fillOpacity={0.06}
              ifOverflow="extendDomain"
            />
            <ReferenceLine
              y={SLO_FLOOR}
              stroke="var(--color-ok)"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
            <ReferenceLine
              y={DANGER_FLOOR}
              stroke="var(--color-danger)"
              strokeDasharray="4 4"
              strokeOpacity={0.4}
            />

            <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} vertical={false} />
            <XAxis
              dataKey="ts"
              type="number"
              domain={["dataMin", "dataMax"]}
              scale="time"
              tickFormatter={(ts: number) => formatRelative(new Date(ts).toISOString())}
              tick={{ fill: "var(--color-text-dim)", fontSize: 11 }}
              stroke="var(--color-border)"
              tickLine={false}
              minTickGap={32}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, DANGER_FLOOR, SLO_FLOOR, 100]}
              tick={{ fill: "var(--color-text-dim)", fontSize: 11 }}
              stroke="var(--color-border)"
              tickLine={false}
              width={44}
            />
            <Tooltip content={<DriftTooltip />} cursor={{ stroke: "var(--color-accent-dim)" }} />
            <Area
              type="monotone"
              dataKey="score"
              stroke="var(--color-accent)"
              strokeWidth={2}
              fill="url(#driftFill)"
              dot={{ r: 2, fill: "var(--color-accent)", strokeWidth: 0 }}
              activeDot={{
                r: 4,
                fill: "var(--color-accent)",
                stroke: "var(--color-bg)",
                strokeWidth: 2,
              }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
