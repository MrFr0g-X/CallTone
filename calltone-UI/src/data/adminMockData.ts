// Role display config used by AdminSidebar and AdminMobileNav for the
// signed-in user's badge label/colour. The previous version of this
// file shipped fake SaaS mock data (clients, billing, MRR, fake
// permissions); that surface area was removed in the pre-defense
// audit because it had no backing functionality.

export type AdminRole = "super_admin" | "admin" | "manager" | "viewer";

export const roleConfig: Record<
  AdminRole,
  { label: string; color: string; bg: string; rank: number }
> = {
  super_admin: { label: "Super Admin", color: "text-accent",            bg: "bg-accent/10",  rank: 0 },
  admin:       { label: "Admin",       color: "text-primary",           bg: "bg-primary/10", rank: 1 },
  manager:     { label: "Manager",     color: "text-warning",           bg: "bg-warning/10", rank: 2 },
  viewer:      { label: "Viewer",      color: "text-muted-foreground",  bg: "bg-muted/40",   rank: 3 },
};
