import type { UserRole } from "@/contexts/AuthContext";
import type { UserCapabilities } from "@/services/api";

export const ADMIN_AREA_ROLES: UserRole[] = ["owner", "super_admin", "admin", "manager", "viewer"];
export const ADMIN_MUTATION_ROLES: UserRole[] = ["owner", "super_admin", "admin"];
export const QA_TOOL_ROLES: UserRole[] = ["qa", "owner", "admin", "super_admin"];

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

export function isPlatformScope(user?: { role?: UserRole | null; clientId?: number | null; roleScope?: "platform" | "tenant" } | null): boolean {
  if (!user) return false;
  if (user.roleScope) return user.roleScope === "platform";
  return (user.role === "owner" || user.role === "super_admin") && user.clientId == null;
}

export function hasCapability(
  capabilities: UserCapabilities | undefined,
  key: keyof UserCapabilities,
  fallback = false,
): boolean {
  return capabilities?.[key] ?? fallback;
}
