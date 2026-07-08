import { describe, expect, it, vi } from "vitest";

import type { User } from "@supabase/supabase-js";

import { getRoles, getRolesFromUser, hasRole } from "./roles";

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
