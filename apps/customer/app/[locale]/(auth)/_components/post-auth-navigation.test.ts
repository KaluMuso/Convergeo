import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getSession = vi.fn();
const getPreferences = vi.fn();

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

import { navigateAfterPortalAuth } from "./post-auth-navigation";

describe("navigateAfterPortalAuth", () => {
  const router = { push: vi.fn(), refresh: vi.fn() };

  beforeEach(() => {
    getSession.mockReset();
    getPreferences.mockReset();
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
    expect(router.push).toHaveBeenCalledWith("/en");
  });
});
