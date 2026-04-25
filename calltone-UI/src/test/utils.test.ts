import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn classname joiner", () => {
  it("joins space-separated strings", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy values", () => {
    const includeB = false;
    expect(cn("a", includeB && "b", null, undefined, "c")).toBe("a c");
  });

  it("merges tailwind-like conflicts (last wins)", () => {
    // tailwind-merge dedupes conflicting utility classes
    expect(cn("px-2", "px-4")).toBe("px-4");
  });
});
