// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithOtp = vi.fn();

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { signInWithOtp },
  }),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: {
      access_token: "token",
      user: { id: "user", email: "vendor@example.com" },
    },
    loading: false,
  }),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

vi.mock("../../listings/new/_lib/ui", () => ({
  Button: ({
    children,
    onClick,
    disabled,
    type = "button",
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    type?: "button" | "submit";
  }) => (
    <button type={type} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  ),
  FormField: ({ label, children }: { label: string; children: React.ReactNode }) => (
    <label>
      {label}
      {children}
    </label>
  ),
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
  Select: (props: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...props} />,
  Spinner: () => null,
}));

vi.mock("../_lib/payouts-client", () => ({
  createPayoutsClient: () => ({ changeMethod: vi.fn() }),
}));

import { PayoutMethodForm } from "./payout-method-form";

beforeEach(() => {
  signInWithOtp.mockResolvedValue({ error: null });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PayoutMethodForm", () => {
  it("sends an email OTP when Send code is clicked", async () => {
    const user = userEvent.setup();
    render(<PayoutMethodForm locale="en" />);

    await user.click(screen.getByRole("button", { name: "payouts.method.sendCode" }));

    await waitFor(() => {
      expect(signInWithOtp).toHaveBeenCalledWith({
        email: "vendor@example.com",
        options: { shouldCreateUser: false },
      });
    });
    expect(screen.getByRole("button", { name: /payouts.method.resendIn/ })).toBeDisabled();
  });
});
