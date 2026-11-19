// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ session: null as unknown }));
vi.mock("../../../../lib/customer-session", () => ({
  useSession: () => ({ session: mocks.session }),
}));

import { MarketingSignInSlot } from "./marketing-sign-in-slot";

afterEach(() => {
  cleanup();
  mocks.session = null;
});

describe("MarketingSignInSlot", () => {
  it("shows Sign in for guests", () => {
    render(<MarketingSignInSlot locale="en" signInLabel="Sign in" accountLabel="My account" />);
    const link = screen.getByRole("link", { name: "Sign in" });
    expect(link).toHaveAttribute("href", "/en/login");
  });

  it("shows My account for a signed-in visitor", () => {
    mocks.session = { user: { id: "u1" } };
    render(<MarketingSignInSlot locale="fr" signInLabel="Sign in" accountLabel="Mon compte" />);
    const link = screen.getByRole("link", { name: "Mon compte" });
    expect(link).toHaveAttribute("href", "/fr/account");
    expect(screen.queryByText("Sign in")).toBeNull();
  });
});
