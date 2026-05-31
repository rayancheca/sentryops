import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SeverityBadge } from "@/components/ui/severity-badge";
import type { Severity } from "@/lib/types";

const CASES: ReadonlyArray<{ severity: Severity; label: string }> = [
  { severity: "low", label: "LOW" },
  { severity: "medium", label: "MED" },
  { severity: "high", label: "HIGH" },
  { severity: "critical", label: "CRIT" },
];

describe("SeverityBadge", () => {
  it.each(CASES)("renders the $label label for $severity", ({ severity, label }) => {
    render(<SeverityBadge severity={severity} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each(CASES)("exposes an accessible severity label for $severity", ({ severity }) => {
    render(<SeverityBadge severity={severity} />);
    expect(screen.getByLabelText(`Severity: ${severity}`)).toBeInTheDocument();
  });

  it("applies the critical variant styling for critical severity", () => {
    render(<SeverityBadge severity="critical" />);
    const badge = screen.getByLabelText("Severity: critical");
    expect(badge.className).toContain("text-critical");
  });

  it("applies the danger variant styling for high severity", () => {
    render(<SeverityBadge severity="high" />);
    const badge = screen.getByLabelText("Severity: high");
    expect(badge.className).toContain("text-danger");
  });

  it("forwards a custom className", () => {
    render(<SeverityBadge severity="low" className="custom-token" />);
    expect(screen.getByLabelText("Severity: low").className).toContain("custom-token");
  });
});
