export type DashboardRange = "Per Call" | "Weekly" | "Monthly" | "Quarterly" | "Yearly" | "Custom";

const RANGE_DAYS: Partial<Record<DashboardRange, number>> = {
  Weekly: 7,
  Monthly: 30,
  Quarterly: 90,
  Yearly: 365,
};

export function isDateInDashboardRange(
  isoDate: string | null | undefined,
  range: DashboardRange,
  now: Date = new Date(),
): boolean {
  if (!isoDate || range === "Per Call" || range === "Custom") return true;
  const days = RANGE_DAYS[range];
  if (!days) return true;

  const timestamp = new Date(isoDate).getTime();
  if (Number.isNaN(timestamp)) return true;

  const cutoff = now.getTime() - days * 24 * 60 * 60 * 1000;
  return timestamp >= cutoff && timestamp <= now.getTime() + 60 * 1000;
}
