// Mirrors the backend's role rules (app/models/user.py). The API enforces
// them; these only decide what the UI offers.
import type { User, UserRole } from "../types";

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  portal_admin: "Portal admin",
  end_user: "End user",
};

const RANK: Record<UserRole, number> = {
  end_user: 0,
  portal_admin: 1,
  admin: 2,
  super_admin: 3,
};

/** Highest first, for pickers. */
export const ALL_ROLES: UserRole[] = ["super_admin", "admin", "portal_admin", "end_user"];

/** Who may open an admin route: any admin role, full admins, or super admins. */
export type AdminAccess = "staff" | "admin" | "super_admin";

export const isStaff = (u: User | null) => !!u && u.role !== "end_user";
export const isAdmin = (u: User | null) =>
  !!u && (u.role === "admin" || u.role === "super_admin");
export const isSuperAdmin = (u: User | null) => u?.role === "super_admin";

export function hasAccess(u: User | null, access: AdminAccess): boolean {
  if (access === "super_admin") return isSuperAdmin(u);
  if (access === "admin") return isAdmin(u);
  return isStaff(u);
}

/** Roles ``actor`` may give to someone. */
export function grantableRoles(actor: User | null): UserRole[] {
  if (isSuperAdmin(actor)) return ALL_ROLES;
  if (!actor || !isAdmin(actor)) return [];
  return ALL_ROLES.filter((r) => RANK[r] <= RANK[actor.role]);
}

/** Whether ``actor`` may edit or delete ``target``'s account. */
export function canManageUser(actor: User | null, target: User): boolean {
  if (isSuperAdmin(actor)) return true;
  return isAdmin(actor) && target.role !== "super_admin";
}
