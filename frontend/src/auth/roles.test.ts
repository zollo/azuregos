import { describe, expect, it } from "vitest";
import type { User, UserRole } from "../types";
import { canManageUser, grantableRoles, hasAccess } from "./roles";

const user = (role: UserRole): User => ({
  id: role,
  email: `${role}@example.com`,
  display_name: role,
  role,
  provider: "local",
  is_active: true,
  created_at: "",
  portal_ids: [],
});

describe("roles", () => {
  it("only lets super admins grant super_admin", () => {
    expect(grantableRoles(user("super_admin"))).toContain("super_admin");
    expect(grantableRoles(user("admin"))).toEqual(["admin", "portal_admin", "end_user"]);
    expect(grantableRoles(user("portal_admin"))).toEqual([]);
  });

  it("keeps admins away from super admin accounts", () => {
    expect(canManageUser(user("admin"), user("super_admin"))).toBe(false);
    expect(canManageUser(user("admin"), user("admin"))).toBe(true);
    expect(canManageUser(user("super_admin"), user("super_admin"))).toBe(true);
  });

  it("gates admin routes by role", () => {
    expect(hasAccess(user("portal_admin"), "staff")).toBe(true);
    expect(hasAccess(user("portal_admin"), "admin")).toBe(false);
    expect(hasAccess(user("admin"), "super_admin")).toBe(false);
    expect(hasAccess(user("end_user"), "staff")).toBe(false);
    expect(hasAccess(null, "staff")).toBe(false);
  });
});
