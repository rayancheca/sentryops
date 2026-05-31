import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusDot, type DotStatus } from "@/components/ui/status-dot";

const STATUSES: ReadonlyArray<DotStatus> = [
  "up",
  "down",
  "open",
  "acknowledged",
  "resolved",
  "closed",
  "unknown",
];

describe("StatusDot", () => {
  it.each(STATUSES)("exposes an accessible status role for %s", (status) => {
    render(<StatusDot status={status} />);
    expect(screen.getByRole("status", { name: `Status: ${status}` })).toBeInTheDocument();
  });

  it("renders a visible label when provided", () => {
    render(<StatusDot status="up" label="Operational" />);
    expect(screen.getByText("Operational")).toBeInTheDocument();
  });

  it("does not render label text when none is provided", () => {
    const { container } = render(<StatusDot status="down" />);
    expect(container.textContent).toBe("");
  });

  it("applies the ok tone for an up status", () => {
    const { container } = render(<StatusDot status="up" />);
    const dot = container.querySelector("span > span");
    expect(dot?.className).toContain("bg-ok");
  });

  it("applies the danger tone for a down status", () => {
    const { container } = render(<StatusDot status="down" />);
    const dot = container.querySelector("span > span");
    expect(dot?.className).toContain("bg-danger");
  });

  it("applies the warn tone for an acknowledged status", () => {
    const { container } = render(<StatusDot status="acknowledged" />);
    const dot = container.querySelector("span > span");
    expect(dot?.className).toContain("bg-warn");
  });

  it("applies the pulse animation when requested", () => {
    const { container } = render(<StatusDot status="open" pulse />);
    const dot = container.querySelector("span > span");
    expect(dot?.className).toContain("animate-pulse-dot");
  });

  it("colors the label text with the status tone", () => {
    render(<StatusDot status="acknowledged" label="Ack" />);
    expect(screen.getByText("Ack").className).toContain("text-warn");
  });
});
