export type AdminRole = "owner" | "super_admin" | "admin" | "manager" | "viewer";

export const roleConfig: Record<
  AdminRole,
  { label: string; color: string; bg: string; rank: number }
> = {
  owner: { label: "Owner", color: "text-emerald-300", bg: "bg-emerald-400/10", rank: 0 },
  super_admin: { label: "Super Admin", color: "text-accent", bg: "bg-accent/10", rank: 1 },
  admin: { label: "Admin", color: "text-primary", bg: "bg-primary/10", rank: 2 },
  manager: { label: "Manager", color: "text-warning", bg: "bg-warning/10", rank: 3 },
  viewer: { label: "Viewer", color: "text-muted-foreground", bg: "bg-muted/40", rank: 4 },
};
