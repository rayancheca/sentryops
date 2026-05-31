// Display formatting helpers for the operator console. Pure and typed — used
// across every data surface for durations, timestamps, percentages, scores.

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_DAY = 86400;

/**
 * Human-readable duration from a number of seconds.
 * e.g. 252 -> "4m 12s", 3661 -> "1h 1m", 90061 -> "1d 1h".
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));

  if (total < SECONDS_PER_MINUTE) return `${total}s`;

  if (total < SECONDS_PER_HOUR) {
    const m = Math.floor(total / SECONDS_PER_MINUTE);
    const s = total % SECONDS_PER_MINUTE;
    return s === 0 ? `${m}m` : `${m}m ${s}s`;
  }

  if (total < SECONDS_PER_DAY) {
    const h = Math.floor(total / SECONDS_PER_HOUR);
    const m = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }

  const d = Math.floor(total / SECONDS_PER_DAY);
  const h = Math.floor((total % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  return h === 0 ? `${d}d` : `${d}d ${h}h`;
}

const RELATIVE_THRESHOLDS: ReadonlyArray<{ limit: number; div: number; unit: string }> = [
  { limit: SECONDS_PER_MINUTE, div: 1, unit: "s" },
  { limit: SECONDS_PER_HOUR, div: SECONDS_PER_MINUTE, unit: "m" },
  { limit: SECONDS_PER_DAY, div: SECONDS_PER_HOUR, unit: "h" },
  { limit: SECONDS_PER_DAY * 30, div: SECONDS_PER_DAY, unit: "d" },
];

/**
 * Compact relative time from an ISO timestamp.
 * e.g. "12s ago", "4m ago", "3h ago", "in 2d".
 */
export function formatRelative(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";

  const deltaSeconds = (Date.now() - then) / 1000;
  const past = deltaSeconds >= 0;
  const abs = Math.abs(deltaSeconds);

  if (abs < 5) return "just now";

  for (const { limit, div, unit } of RELATIVE_THRESHOLDS) {
    if (abs < limit) {
      const value = Math.floor(abs / div);
      return past ? `${value}${unit} ago` : `in ${value}${unit}`;
    }
  }

  const months = Math.floor(abs / (SECONDS_PER_DAY * 30));
  if (months < 12) return past ? `${months}mo ago` : `in ${months}mo`;

  const years = Math.floor(abs / (SECONDS_PER_DAY * 365));
  return past ? `${years}y ago` : `in ${years}y`;
}

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/**
 * Absolute, sortable timestamp for tooltips and audit rows.
 * e.g. "May 31, 2026, 14:03:21".
 */
export function formatDateTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "—";
  return DATE_TIME_FORMATTER.format(new Date(ts));
}

/**
 * Percentage from either a 0..1 fraction or a 0..100 value.
 * Values <= 1 are treated as fractions; anything larger is treated as a
 * pre-scaled percent. e.g. 0.9732 -> "97.3%", 99.95 -> "100%".
 */
export function formatPercent(value: number, fractionDigits = 1): string {
  if (!Number.isFinite(value)) return "—";
  const pct = value <= 1 ? value * 100 : value;
  const clamped = Math.min(100, Math.max(0, pct));
  return `${clamped.toFixed(fractionDigits)}%`;
}

/**
 * Score formatter for compliance/triage gauges. Rounds to whole points and
 * clamps to the 0..100 band the rings expect.
 */
export function formatScore(num: number): string {
  if (!Number.isFinite(num)) return "—";
  const clamped = Math.min(100, Math.max(0, num));
  return Math.round(clamped).toString();
}
