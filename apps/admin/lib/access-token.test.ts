// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

const session = vi.hoisted(() => ({ value: null as { access_token: string } | null }));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { getSession: async () => ({ data: { session: session.value } }) },
  }),
}));

import { getBrowserAccessToken } from "./access-token";

beforeEach(() => {
  session.value = null;
});

describe("getBrowserAccessToken (lazy)", () => {
  it("returns the live session token", async () => {
    session.value = { access_token: "tok" };
    await expect(getBrowserAccessToken()).resolves.toBe("tok");
  });

  it("returns null without a session", async () => {
    await expect(getBrowserAccessToken()).resolves.toBeNull();
  });
});
