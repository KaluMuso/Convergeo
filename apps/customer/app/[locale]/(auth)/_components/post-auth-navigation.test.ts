import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getSession, getPreferences, mergeGuestCartIntoAccount } = vi.hoisted(() => ({
  getSession: vi.fn(),
  getPreferences: vi.fn(),
  mergeGuestCartIntoAccount: vi.fn(),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { getSession },
  }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({
    getPreferences,
  }),
}));

vi.mock("../../../../lib/cart-merge", () => ({
  mergeGuestCartIntoAccount,
}));

import { navigateAfterPortalAuth } from "./post-auth-navigation";

describe("navigateAfterPortalAuth", () => {
  const router = { push: vi.fn(), refresh: vi.fn() };

  beforeEach(() => {
    getSession.mockReset();
    getPreferences.mockReset();
    mergeGuestCartIntoAccount.mockReset();
    mergeGuestCartIntoAccount.mockResolvedValue(undefined);
    router.push.mockReset();
    router.refresh.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("customer email auth still loads preferences and welcome when onboarding is incomplete", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    getPreferences.mockResolvedValue({ onboarding: { completed_at: null } });

    await navigateAfterPortalAuth({
      router,
      locale: "en",
      portal: "customer",
      nextParam: "/en/account",
      fallbackPath: "/en",
    });

    expect(getPreferences).toHaveBeenCalledOnce();
    expect(mergeGuestCartIntoAccount).toHaveBeenCalledWith("tok");
    expect(mergeGuestCartIntoAccount.mock.invocationCallOrder[0]).toBeLessThan(
      getPreferences.mock.invocationCallOrder[0]!,
    );
    expect(getPreferences.mock.invocationCallOrder[0]).toBeLessThan(
      router.push.mock.invocationCallOrder[0]!,
    );
    expect(router.push).toHaveBeenCalledWith("/en/welcome?next=%2Fen%2Faccount");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("customer email auth preserves the destination when onboarding is complete", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    getPreferences.mockResolvedValue({
      onboarding: { completed_at: "2026-08-13T00:00:00Z" },
    });

    await navigateAfterPortalAuth({
      router,
      locale: "en",
      portal: "customer",
      nextParam: "/en/account",
      fallbackPath: "/en",
    });

    expect(getPreferences).toHaveBeenCalledOnce();
    expect(router.push).toHaveBeenCalledWith("/en/account");
  });

  it("vendor email auth never calls customer preferences and uses a safe destination", async () => {
    await navigateAfterPortalAuth({
      router,
      locale: "en",
      portal: "vendor",
      nextParam: "/en/listings",
      fallbackPath: "/en",
    });

    expect(getSession).not.toHaveBeenCalled();
    expect(mergeGuestCartIntoAccount).not.toHaveBeenCalled();
    expect(getPreferences).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith("/en/listings");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("vendor email auth rejects an external next value", async () => {
    await navigateAfterPortalAuth({
      router,
      locale: "en",
      portal: "vendor",
      nextParam: "https://evil.example",
      fallbackPath: "/en",
    });

    expect(getPreferences).not.toHaveBeenCalled();
    expect(mergeGuestCartIntoAccount).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith("/en");
  });

  it("admin email auth never calls customer preferences", async () => {
    await navigateAfterPortalAuth({
      router,
      locale: "fr",
      portal: "admin",
      nextParam: "/fr/kyc",
      fallbackPath: "/fr",
    });

    expect(getPreferences).not.toHaveBeenCalled();
    expect(mergeGuestCartIntoAccount).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith("/fr/kyc");
  });

  it("oauth callback uses the same portal-aware destinations", async () => {
    await navigateAfterPortalAuth({
      router,
      locale: "en",
      portal: "vendor",
      nextParam: "//evil.example",
      fallbackPath: "/en",
    });

    expect(getPreferences).not.toHaveBeenCalled();
    expect(mergeGuestCartIntoAccount).not.toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith("/en");
  });

  it("fails closed when the Customer cart merge fails", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    mergeGuestCartIntoAccount.mockRejectedValue(new Error("merge failed"));

    await expect(
      navigateAfterPortalAuth({
        router,
        locale: "en",
        portal: "customer",
        nextParam: "/en/account",
        fallbackPath: "/en",
      }),
    ).rejects.toThrow("merge failed");

    expect(getPreferences).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
    expect(router.refresh).not.toHaveBeenCalled();
  });
});
