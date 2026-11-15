import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: null }),
}));

import { liveShopCount } from "./businesses-overview";

import type { Business } from "../_lib/businesses-client";

const branch = (id: string, branch_status: string, status = "active") => ({
  id,
  slug: id,
  display_name: id,
  status,
  branch_status,
  branch_kind: "physical",
  is_primary: id === "main",
  payout_on_hold: false,
  review_note: null,
});

describe("liveShopCount", () => {
  it("counts only approved, active shops (what customers see as Other branches)", () => {
    const business = {
      branches: [
        branch("main", "approved"),
        branch("kabwata", "approved"),
        branch("matero", "pending_review", "draft"),
        branch("suspended", "approved", "suspended"),
      ],
    } as unknown as Business;
    expect(liveShopCount(business)).toBe(2);
  });
});
