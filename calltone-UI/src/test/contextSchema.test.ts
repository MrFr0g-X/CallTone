import { describe, it, expect } from "vitest";
import { toContextGroups } from "@/lib/contextSchema";

describe("toContextGroups", () => {
  it("reads the grouped schema and marks filled vs empty", () => {
    const g = toContextGroups({
      company_name: "metro boost",
      script_compliance: { greeting_script: "Hi, thanks for calling", closing_script: "" },
      factual_accuracy: { products_and_services: "fibre, mobile" },
      behavioral: { tone_guidelines: "" },
      atomic_nodes: [{ id: 1 }, { id: 2 }],
    });
    const sc = g.groups.find((x) => x.key === "script_compliance")!;
    expect(sc.fields.find((f) => f.key === "greeting_script")!.filled).toBe(true);
    expect(sc.fields.find((f) => f.key === "closing_script")!.filled).toBe(false);
    expect(g.atomicNodeCount).toBe(2);
    expect(g.filledCount).toBe(2); // greeting_script + products_and_services
  });

  it("falls back to flat legacy schema", () => {
    const g = toContextGroups({ company_name: "X", greeting_script: "Hello" });
    expect(g.filledCount).toBe(1);
    expect(g.groups.some((grp) => grp.fields.some((f) => f.key === "greeting_script" && f.filled))).toBe(true);
  });
});
