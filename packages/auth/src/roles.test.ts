import { describe, expect, it, vi } from "vitest";

import type { User } from "@supabase/supabase-js";

import { getRoles, getRolesFromClaims, getRolesFromUser, hasRole } from "./roles";

function makeUser(roles: string[] | undefined): User {
  return {
    id: "user-1",
    app_metadata: roles ? { roles } : {},
    aud: "authenticated",
    created_at: "2026-01-01T00:00:00.000Z",
  } as User;
}

describe("hasRole", () => {
  it("returns true when the role is present", () => {
    expect(hasRole(["customer", "vendor"], "vendor")).toBe(true);
  });

  it("returns false when the role is absent", () => {
    expect(hasRole(["customer"], "admin")).toBe(false);
  });
});

describe("getRolesFromUser", () => {
  it("reads roles from JWT app_metadata for middleware fast-path", () => {
    expect(getRolesFromUser(makeUser(["vendor", "customer"]))).toEqual(["vendor", "customer"]);
  });

  it("filters unknown roles", () => {
    expect(getRolesFromUser(makeUser(["vendor", "superuser"]))).toEqual(["vendor"]);
  });

  it("returns an empty list for missing users", () => {
    expect(getRolesFromUser(null)).toEqual([]);
  });
});

describe("getRolesFromClaims", () => {
  it("reads roles from verified access token claims (app_metadata.roles)", () => {
    expect(getRolesFromClaims({ app_metadata: { roles: ["customer", "vendor"] } })).toEqual([
      "customer",
      "vendor",
    ]);
  });

  it("filters unknown role strings", () => {
    expect(getRolesFromClaims({ app_metadata: { roles: ["vendor", "superuser"] } })).toEqual([
      "vendor",
    ]);
  });

  it("filters non-string entries", () => {
    expect(getRolesFromClaims({ app_metadata: { roles: ["vendor", 123, null, {}] } })).toEqual([
      "vendor",
    ]);
  });

  it("fails closed when app_metadata.roles is not an array", () => {
    expect(getRolesFromClaims({ app_metadata: { roles: "vendor" } })).toEqual([]);
  });

  it("fails closed when app_metadata is missing", () => {
    expect(getRolesFromClaims({})).toEqual([]);
  });

  it("fails closed when app_metadata is not an object", () => {
    expect(getRolesFromClaims({ app_metadata: "vendor" })).toEqual([]);
  });

  it("fails closed on non-object claims", () => {
    expect(getRolesFromClaims(null)).toEqual([]);
    expect(getRolesFromClaims(undefined)).toEqual([]);
    expect(getRolesFromClaims("vendor")).toEqual([]);
    expect(getRolesFromClaims(42)).toEqual([]);
  });

  it("never trusts user_metadata as a role source, even if app_metadata is absent", () => {
    expect(getRolesFromClaims({ user_metadata: { roles: ["vendor"] } })).toEqual([]);
  });

  it("never trusts user_metadata even alongside a role-less app_metadata", () => {
    expect(getRolesFromClaims({ app_metadata: {}, user_metadata: { roles: ["admin"] } })).toEqual(
      [],
    );
  });
});

describe("getRoles", () => {
  it("reads authoritative roles from public.user_roles", async () => {
    const supabase = {
      from: vi.fn().mockReturnValue({
        select: vi.fn().mockReturnValue({
          eq: vi.fn().mockResolvedValue({
            data: [{ role: "vendor" }, { role: "customer" }],
            error: null,
          }),
        }),
      }),
    };

    await expect(getRoles(supabase as never, "user-1")).resolves.toEqual(["vendor", "customer"]);
    expect(supabase.from).toHaveBeenCalledWith("user_roles");
  });
});
