import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";

const BAND_OK = 90;
const BAND_WARN = 70;

// Color band: >=90 ok, >=70 warn, else danger. Returns the CSS var the SVG
// stroke + label reference so the gauge stays on the semantic palette.
function bandColor(score: number): string {
  if (score >= BAND_OK) return "var(--color-ok)";
  if (score >= BAND_WARN) return "var(--color-warn)";
  return "var(--color-danger)";
}

export interface ScoreRingProps {
  /** 0..100 score. */
  score: number;
  /** Outer diameter in pixels. */
  size?: number;
  className?: string;
}

export function ScoreRing({ score, size = 96, className }: ScoreRingProps) {
  const clamped = Math.min(100, Math.max(0, Number.isFinite(score) ? score : 0));
  const stroke = Math.max(4, Math.round(size * 0.08));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const color = bandColor(clamped);

  return (
    <div
      className={cn("relative inline-flex shrink-0", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Score ${formatScore(clamped)} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
        />
      </svg>
      <span
        className="tabular absolute inset-0 flex items-center justify-center font-semibold"
        style={{ color, fontSize: size * 0.28 }}
      >
        {formatScore(clamped)}
      </span>
    </div>
  );
}
