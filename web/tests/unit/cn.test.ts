import { describe, expect, it } from "vitest";

import { cn } from "@/lib/cn";

describe("cn", () => {
  it("joins plain class names", () => {
    expect(cn("a", "b", "c")).toBe("a b c");
  });

  it("drops falsy conditional values", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
  });

  it("flattens arrays and objects via clsx", () => {
    expect(cn(["a", "b"], { c: true, d: false })).toBe("a b c");
  });

  it("resolves conflicting Tailwind utilities, last one wins", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("keeps non-conflicting Tailwind utilities", () => {
    expect(cn("px-2", "py-4")).toBe("px-2 py-4");
  });

  it("merges a base class with a conditional override", () => {
    expect(cn("bg-red-500", true && "bg-blue-500")).toBe("bg-blue-500");
  });

  it("returns an empty string with no input", () => {
    expect(cn()).toBe("");
  });
});
