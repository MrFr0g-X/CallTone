import { describe, expect, it } from "vitest";
import { canManageAdminUsers, canUseQaTools, roleHome } from "@/lib/roles";

describe("role helpers", () => {
  it("routes each role to its correct home surface", () => {
    expect(roleHome("agent")).toBe("/agent/dashboard");
    expect(roleHome("qa")).toBe("/qa/dashboard");
    expect(roleHome("owner")).toBe("/admin/dashboard");
    expect(roleHome("admin")).toBe("/admin/dashboard");
    expect(roleHome("super_admin")).toBe("/admin/dashboard");
    expect(roleHome("manager")).toBe("/admin/dashboard");
    expect(roleHome("viewer")).toBe("/admin/dashboard");
  });

  it("limits admin mutations to admin and super admin", () => {
    expect(canManageAdminUsers("owner")).toBe(true);
    expect(canManageAdminUsers("super_admin")).toBe(true);
    expect(canManageAdminUsers("admin")).toBe(true);
    expect(canManageAdminUsers("manager")).toBe(false);
    expect(canManageAdminUsers("viewer")).toBe(false);
    expect(canManageAdminUsers("qa")).toBe(false);
  });

  it("limits QA tooling to QA and admin operators", () => {
    expect(canUseQaTools("qa")).toBe(true);
    expect(canUseQaTools("owner")).toBe(true);
    expect(canUseQaTools("admin")).toBe(true);
    expect(canUseQaTools("super_admin")).toBe(true);
    expect(canUseQaTools("agent")).toBe(false);
  });
});
