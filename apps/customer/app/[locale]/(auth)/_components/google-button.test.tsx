// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithOAuth = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { signInWithOAuth },
  }),
}));

import { GoogleButton } from "./google-button";

describe("GoogleButton", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    signInWithOAuth.mockResolvedValue({ error: null });
  });

  it("does not render a usable Google button when the provider flag is off", () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_AUTH_ENABLED", undefined);
    render(
      <GoogleButton
        label="Continue with Google"
        loadingLabel="Connecting to Google"
        locale="en"
        nextPath="/en"
        onError={() => undefined}
      />,
    );

    expect(screen.queryByRole("button", { name: "Continue with Google" })).not.toBeInTheDocument();
  });

  it("starts the Google OAuth flow when the flag is enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_AUTH_ENABLED", "true");
    const user = userEvent.setup();
    render(
      <GoogleButton
        label="Continue with Google"
        loadingLabel="Connecting to Google"
        locale="en"
        nextPath="/en/account"
        onError={() => undefined}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Continue with Google" }));

    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: expect.stringContaining("/en/login?next=%2Fen%2Faccount"),
      },
    });
  });

  it("sanitizes an unsafe next path before starting OAuth", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_AUTH_ENABLED", "true");
    const user = userEvent.setup();
    render(
      <GoogleButton
        label="Continue with Google"
        loadingLabel="Connecting to Google"
        locale="en"
        nextPath="https://evil.example"
        onError={() => undefined}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Continue with Google" }));

    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: expect.stringContaining("/en/login?next=%2Fen"),
      },
    });
    expect(signInWithOAuth.mock.calls[0]?.[0].options.redirectTo).not.toContain("evil.example");
  });
});
