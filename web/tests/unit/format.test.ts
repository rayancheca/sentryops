import { describe, expect, it } from "vitest";

import {
  formatDateTime,
  formatDuration,
  formatPercent,
  formatRelative,
  formatScore,
} from "@/lib/format";

describe("formatDuration", () => {
  it("renders sub-minute values as bare seconds", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(1)).toBe("1s");
    expect(formatDuration(59)).toBe("59s");
  });

  it("renders minute-and-second values", () => {
    expect(formatDuration(90)).toBe("1m 30s");
    expect(formatDuration(252)).toBe("4m 12s");
  });

  it("drops the seconds component when it is zero", () => {
    expect(formatDuration(60)).toBe("1m");
    expect(formatDuration(120)).toBe("2m");
  });

  it("renders hour-and-minute values past an hour", () => {
    // 3750s = 1h 2m 30s -> minutes floored, seconds dropped at the hour band
    expect(formatDuration(3750)).toBe("1h 2m");
    expect(formatDuration(3661)).toBe("1h 1m");
  });

  it("drops the minutes component when it is zero at the hour band", () => {
    expect(formatDuration(3600)).toBe("1h");
  });

  it("renders day-and-hour values past a day", () => {
    expect(formatDuration(90061)).toBe("1d 1h");
    expect(formatDuration(86400)).toBe("1d");
  });

  it("rounds and floors negatives to zero", () => {
    expect(formatDuration(0.4)).toBe("0s");
    expect(formatDuration(-10)).toBe("0s");
  });

  it("returns the em dash for non-finite input", () => {
    expect(formatDuration(Number.NaN)).toBe("—");
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("formatScore", () => {
  it("rounds to whole points", () => {
    expect(formatScore(72.4)).toBe("72");
    expect(formatScore(72.6)).toBe("73");
  });

  it("clamps to the 0..100 band", () => {
    expect(formatScore(-5)).toBe("0");
    expect(formatScore(150)).toBe("100");
  });

  it("returns the em dash for non-finite input", () => {
    expect(formatScore(Number.NaN)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("treats values <= 1 as fractions", () => {
    expect(formatPercent(0.9732)).toBe("97.3%");
    expect(formatPercent(0.5)).toBe("50.0%");
    expect(formatPercent(1)).toBe("100.0%");
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("treats values > 1 as pre-scaled percents", () => {
    expect(formatPercent(50)).toBe("50.0%");
    expect(formatPercent(97.32)).toBe("97.3%");
  });

  it("clamps a pre-scaled value to 100", () => {
    expect(formatPercent(99.95)).toBe("100.0%");
    expect(formatPercent(250)).toBe("100.0%");
  });

  it("respects the fractionDigits argument", () => {
    expect(formatPercent(0.9732, 0)).toBe("97%");
    expect(formatPercent(0.9732, 2)).toBe("97.32%");
  });

  it("returns the em dash for non-finite input", () => {
    expect(formatPercent(Number.NaN)).toBe("—");
  });
});

describe("formatRelative", () => {
  it("returns 'just now' for very recent timestamps", () => {
    expect(formatRelative(new Date().toISOString())).toBe("just now");
  });

  it("renders past durations with an 'ago' suffix", () => {
    const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(formatRelative(tenMinutesAgo)).toMatch(/^\d+m ago$/);
  });

  it("renders future durations with an 'in' prefix", () => {
    const inTwoHours = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
    expect(formatRelative(inTwoHours)).toMatch(/^in \d+h$/);
  });

  it("returns the em dash for an unparseable timestamp", () => {
    expect(formatRelative("not-a-date")).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("renders a stable absolute timestamp shape", () => {
    const result = formatDateTime("2026-05-31T14:03:21Z");
    // Locale-formatted: month abbrev, day, year, and a 24h time component.
    expect(result).toMatch(/2026/);
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("returns the em dash for an unparseable timestamp", () => {
    expect(formatDateTime("nope")).toBe("—");
  });
});
