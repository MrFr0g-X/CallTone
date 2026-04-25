import { describe, expect, it } from "vitest";
import { isDateInDashboardRange } from "@/lib/timeRange";

describe("isDateInDashboardRange", () => {
  const now = new Date("2026-04-24T12:00:00Z");

  it("keeps calls inside the selected dashboard range", () => {
    expect(isDateInDashboardRange("2026-04-20T12:00:00Z", "Weekly", now)).toBe(true);
    expect(isDateInDashboardRange("2026-03-30T12:00:00Z", "Monthly", now)).toBe(true);
    expect(isDateInDashboardRange("2026-02-01T12:00:00Z", "Quarterly", now)).toBe(true);
  });

  it("filters calls outside the selected dashboard range", () => {
    expect(isDateInDashboardRange("2026-04-01T12:00:00Z", "Weekly", now)).toBe(false);
    expect(isDateInDashboardRange("2026-01-01T12:00:00Z", "Monthly", now)).toBe(false);
  });

  it("does not hide undated or per-call rows", () => {
    expect(isDateInDashboardRange(null, "Weekly", now)).toBe(true);
    expect(isDateInDashboardRange("2024-01-01T00:00:00Z", "Per Call", now)).toBe(true);
  });
});
