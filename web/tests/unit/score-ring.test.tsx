import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreRing } from "@/components/ui/score-ring";

describe("ScoreRing", () => {
  it("renders the rounded score as text", () => {
    render(<ScoreRing score={82.6} />);
    expect(screen.getByText("83")).toBeInTheDocument();
  });

  it("exposes an accessible score label out of 100", () => {
    render(<ScoreRing score={91} />);
    expect(screen.getByRole("img", { name: "Score 91 out of 100" })).toBeInTheDocument();
  });

  it("uses the ok color band for scores >= 90", () => {
    render(<ScoreRing score={95} />);
    const label = screen.getByText("95");
    expect(label).toHaveStyle({ color: "var(--color-ok)" });
  });

  it("uses the warn color band for scores >= 70 and < 90", () => {
    render(<ScoreRing score={75} />);
    const label = screen.getByText("75");
    expect(label).toHaveStyle({ color: "var(--color-warn)" });
  });

  it("uses the danger color band for scores < 70", () => {
    render(<ScoreRing score={40} />);
    const label = screen.getByText("40");
    expect(label).toHaveStyle({ color: "var(--color-danger)" });
  });

  it("clamps out-of-range scores into the 0..100 band", () => {
    render(<ScoreRing score={150} />);
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("falls back to zero for non-finite scores", () => {
    render(<ScoreRing score={Number.NaN} />);
    const label = screen.getByText("0");
    expect(label).toBeInTheDocument();
    expect(label).toHaveStyle({ color: "var(--color-danger)" });
  });

  it("respects a custom size on the wrapper", () => {
    render(<ScoreRing score={50} size={128} />);
    const wrapper = screen.getByRole("img", { name: /Score 50/ });
    expect(wrapper).toHaveStyle({ width: "128px", height: "128px" });
  });
});
