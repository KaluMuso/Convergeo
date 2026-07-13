// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import accountMessages from "../../../../../../packages/i18n/messages/en/account.json";

const request = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "en" }),
}));

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request }),
}));

vi.mock("@vergeo/auth/browser-client", () => ({
  createBrowserClient: () => ({
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      getUser: vi.fn().mockResolvedValue({ data: { user: { phone: "260971234567" } } }),
      signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import AccountPrivacyPage from "./page";

const privacy = accountMessages.privacy;

function renderPage() {
  return render(
    <NextIntlClientProvider
      locale="en"
      messages={{ account: accountMessages }}
      onError={(error) => {
        // Any intl error (MISSING_MESSAGE above all) must fail the test — this
        // page crashed at runtime when its keys were absent from account.json
        // (M04-P06 debt, docs/plan/i18n-audit.md).
        throw error;
      }}
    >
      <AccountPrivacyPage />
    </NextIntlClientProvider>,
  );
}

describe("account privacy (DPA) page i18n", () => {
  it("renders intro, export, and delete sections from real EN messages", async () => {
    renderPage();

    // Intro
    expect(screen.getByRole("heading", { name: privacy.title })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: privacy.backToAccount })).toHaveAttribute(
      "href",
      "/en/account",
    );
    expect(screen.getByText(privacy.retentionNote)).toBeInTheDocument();

    // Export section
    expect(screen.getByRole("heading", { name: privacy.export.title })).toBeInTheDocument();
    expect(screen.getByText(privacy.export.description)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: privacy.export.button })).toBeEnabled();
    expect(screen.getByRole("link", { name: privacy.export.policyLink })).toHaveAttribute(
      "href",
      "/en/legal/privacy",
    );

    // Delete section
    expect(screen.getByRole("heading", { name: privacy.delete.title })).toBeInTheDocument();
    expect(screen.getByText(privacy.delete.warning)).toBeInTheDocument();
    expect(screen.getByLabelText(privacy.delete.confirmPhraseLabel)).toHaveAttribute(
      "placeholder",
      privacy.delete.confirmPhraseHint,
    );
    expect(screen.getByRole("group", { name: privacy.delete.otpAria })).toBeInTheDocument();
    // ICU placeholders ({position}, {total}) interpolate per OTP digit.
    expect(screen.getByLabelText("Digit 1 of 6")).toBeInTheDocument();
    expect(screen.getByLabelText("Digit 6 of 6")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: privacy.delete.submit })).toBeDisabled();

    // Verified phone loads async; the send-code button then becomes enabled.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: privacy.delete.sendOtp })).toBeEnabled(),
    );
  });

  it("shows the localized download link after a successful export request", async () => {
    request.mockResolvedValue({
      export_id: "exp-1",
      download_url: "https://files.example/export.json",
      expires_in_seconds: 3600,
    });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: privacy.delete.sendOtp })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: privacy.export.button }));

    const download = await screen.findByRole("link", { name: privacy.export.success });
    expect(download).toHaveAttribute("href", "https://files.example/export.json");
    expect(request).toHaveBeenCalledWith("/account/export", { method: "POST" });
  });
});
