import type { UserRole } from "@/contexts/AuthContext";
import type { UserCapabilities } from "@/services/api";

export const ADMIN_AREA_ROLES: UserRole[] = ["owner", "super_admin", "admin", "manager", "viewer"];
export const ADMIN_MUTATION_ROLES: UserRole[] = ["owner", "super_admin", "admin"];
export const QA_TOOL_ROLES: UserRole[] = ["qa", "owner", "admin", "super_admin"];

// Platform roles are CallTone-internal (owner = CallTone owner, super_admin = CallTone
// staff). Company tenants must never see or assign them. Tenant-assignable roles are the
// company-level roles only.
export const PLATFORM_ROLES: UserRole[] = ["owner", "super_admin"];
export const TENANT_ASSIGNABLE_ROLES: UserRole[] = ["admin", "manager", "qa", "agent", "viewer"];

// Roles an actor may see in filters / assign in menus. Platform users (CallTone staff)
// see every role; tenant users see only the company-level roles.
export function assignableRolesFor(
  user?: { role?: UserRole | null; clientId?: number | null; roleScope?: "platform" | "tenant" } | null,
): UserRole[] {
  return isPlatformScope(user)
    ? ["owner", "super_admin", ...TENANT_ASSIGNABLE_ROLES]
    : [...TENANT_ASSIGNABLE_ROLES];
}

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
