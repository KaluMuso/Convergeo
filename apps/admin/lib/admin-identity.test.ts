import { describe, expect, it } from "vitest";

import { adminDisplayName, readAdminIdentity, resolveAdminRoleKind } from "./admin-identity";

describe("resolveAdminRoleKind", () => {
  it("maps grants to the label shown in the top bar", () => {
    expect(resolveAdminRoleKind({ unrestricted: true, can_manage_roles: true })).toBe("superadmin");
    expect(resolveAdminRoleKind({ unrestricted: true, can_manage_roles: false })).toBe("admin");
    expect(resolveAdminRoleKind({ unrestricted: false, can_manage_roles: false })).toBe("custom");
    expect(resolveAdminRoleKind(null)).toBeNull();
  });
});

describe("identity", () => {
  it("prefers the profile name and falls back to the email local part", () => {
    const named = readAdminIdentity({ email: "a@b.zm", user_metadata: { full_name: " Amina " } });
    expect(adminDisplayName(named)).toBe("Amina");
    expect(adminDisplayName({ email: "chanda@vergeo5.com", name: null })).toBe("chanda");
    expect(adminDisplayName(readAdminIdentity(null))).toBeNull();
  });
});
