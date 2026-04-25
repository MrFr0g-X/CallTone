import type { UserRole } from "@/contexts/AuthContext";

export const ADMIN_AREA_ROLES: UserRole[] = ["super_admin", "admin", "manager", "viewer"];
export const ADMIN_MUTATION_ROLES: UserRole[] = ["super_admin", "admin"];
export const QA_TOOL_ROLES: UserRole[] = ["qa", "admin", "super_admin"];

export function roleHome(role?: UserRole | null): string {
  if (!role) return "/login";
  if (ADMIN_AREA_ROLES.includes(role)) return "/admin/dashboard";
  if (role === "qa") return "/qa/dashboard";
  return "/agent/dashboard";
}

export function canManageAdminUsers(role?: UserRole | null): boolean {
  return !!role && ADMIN_MUTATION_ROLES.includes(role);
}

export function canUseQaTools(role?: UserRole | null): boolean {
  return !!role && QA_TOOL_ROLES.includes(role);
}
