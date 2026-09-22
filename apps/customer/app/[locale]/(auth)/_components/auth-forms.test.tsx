// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithOtp = vi.fn();
const verifyOtp = vi.fn();
const exchangeCodeForSession = vi.fn();
const getSession = vi.fn();
const getPreferences = vi.fn();
const { getReadyCustomerSession } = vi.hoisted(() => ({
  getReadyCustomerSession: vi.fn(),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      signInWithOtp,
      verifyOtp,
      exchangeCodeForSession,
      getSession,
    },
  }),
}));

vi.mock("../../account/_components/account-api", () => ({
  createAccountApiClient: () => ({
    getPreferences,
  }),
}));

vi.mock("../../../../lib/customer-session", () => ({
  getReadyCustomerSession,
}));

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

beforeEach(() => {
  signInWithOtp.mockResolvedValue({ error: null });
  verifyOtp.mockResolvedValue({ error: null });
  getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
  getPreferences.mockResolvedValue({
    onboarding: { completed_at: "2026-01-01T00:00:00Z" },
  });
  getReadyCustomerSession.mockResolvedValue({ access_token: "tok" });
});

import { OtpForm } from "./otp-form";
import { PhoneForm } from "./phone-form";
import { ResendCountdown } from "./resend-countdown";

const phoneLabels = {
  countryCode: "Country code",
  nationalNumber: "Phone number",
  phoneLabel: "Mobile number",
  phoneHelp: "SMS help",
  phonePlaceholder: "97 123 4567",
  submit: "Continue",
  loading: "Loading",
  required: "Required",
  invalidPhone: "Invalid phone",
  sendFailed: "Send failed",
  throttled: "Try again in {seconds} seconds",
};

const otpLabels = {
  ariaGroup: "Verification code",
  digitLabel: "Digit {position} of {total}",
  submit: "Verify",
  loading: "Verifying",
  resend: "Resend code",
  resendIn: "Resend in {seconds}s",
  changePhone: "Change phone",
  wrongCode: "Wrong code",
  expired: "Expired",
  throttled: "Try again in {seconds} seconds",
  generic: "Generic error",
  sendFailed: "Send failed",
};

describe("PhoneForm", () => {
  it("routes to OTP after successful phone submit", async () => {
    const user = userEvent.setup();
    render(<PhoneForm locale="en" labels={phoneLabels} otpPath="/otp" />);

    await user.type(screen.getByLabelText("Phone number"), "971234567");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(signInWithOtp).toHaveBeenCalledWith({
        phone: "+260971234567",
        options: { shouldCreateUser: false },
      });
      expect(push).toHaveBeenCalledWith("/en/otp?phone=%2B260971234567");
    });
  });

  /**
   * Run #70 product defect: middleware bounces a protected route to
   * `/{locale}/login?next=<destination>`, the login page reads `next`
   * correctly, and AuthLoginShell forwarded it to the email/OAuth legs — but
   * PhoneForm built its OTP URL from `{ phone }` alone, so the phone leg threw
   * the destination away and every phone login landed on the portal home.
   */
  it("carries a safe next destination into the OTP URL", async () => {
    const user = userEvent.setup();
    render(<PhoneForm locale="en" labels={phoneLabels} otpPath="/otp" nextParam="/en/services" />);

    await user.type(screen.getByLabelText("Phone number"), "971234567");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/en/otp?phone=%2B260971234567&next=%2Fen%2Fservices");
    });
  });

  it("preserves a deeper destination path unchanged", async () => {
    const user = userEvent.setup();
    render(
      <PhoneForm
        locale="en"
        labels={phoneLabels}
        otpPath="/otp"
        nextParam="/en/events/synthetic-event/scan"
      />,
    );

    await user.type(screen.getByLabelText("Phone number"), "971234567");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const target = new URL(String(push.mock.calls.at(-1)?.[0]), "https://vendor.test");
    expect(target.pathname).toBe("/en/otp");
    expect(target.searchParams.get("phone")).toBe("+260971234567");
    expect(target.searchParams.get("next")).toBe("/en/events/synthetic-event/scan");
  });

  it("without a next param, the OTP URL is byte-identical to the previous behavior", async () => {
    const user = userEvent.setup();
    render(<PhoneForm locale="en" labels={phoneLabels} otpPath="/otp" nextParam={null} />);

    await user.type(screen.getByLabelText("Phone number"), "971234567");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/en/otp?phone=%2B260971234567");
    });
  });

  it("refuses to echo an attacker-controlled external destination into the OTP URL", async () => {
    const user = userEvent.setup();
    render(
      <PhoneForm
        locale="en"
        labels={phoneLabels}
        otpPath="/otp"
        nextParam="https://evil.test/steal"
      />,
    );

    await user.type(screen.getByLabelText("Phone number"), "971234567");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/en/otp?phone=%2B260971234567");
    });
    expect(String(push.mock.calls.at(-1)?.[0])).not.toContain("evil.test");
  });
});

describe("OtpForm", () => {
  async function fillOtp(user: ReturnType<typeof userEvent.setup>) {
    const group = screen.getByRole("group", { name: "Verification code" });
    const inputs = group.querySelectorAll("input");
    for (let index = 0; index < 6; index += 1) {
      await user.type(inputs[index]!, String(index + 1));
    }
  }

  it("shows wrong-code error on invalid OTP", async () => {
    verifyOtp.mockResolvedValue({ error: { message: "Invalid OTP" } });
    const user = userEvent.setup();

    render(
      <OtpForm
        locale="en"
        phone="+260971234567"
        labels={otpLabels}
        loginPath="/login"
        defaultNextPath="/en"
      />,
    );

    await fillOtp(user);
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Wrong code");
    });
  });

  it("shows throttled retry-after message", async () => {
    verifyOtp.mockResolvedValue({ error: { status: 429, retryAfter: 42 } });
    const user = userEvent.setup();

    render(
      <OtpForm
        locale="en"
        phone="+260971234567"
        labels={otpLabels}
        loginPath="/login"
        defaultNextPath="/en"
      />,
    );

    await fillOtp(user);
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Try again in 42 seconds");
    });
  });

  it("completes happy path on valid OTP", async () => {
    verifyOtp.mockResolvedValue({ error: null });
    const user = userEvent.setup();

    render(
      <OtpForm
        locale="en"
        phone="+260971234567"
        labels={otpLabels}
        loginPath="/login"
        defaultNextPath="/en"
      />,
    );

    // No Verify click: OtpField auto-submits on the sixth digit, so filling the
    // code IS the submission. On success the form stays locked through the
    // navigation transition (the button reads "Verifying"), which is the whole
    // point of the single-flight guard — see the OtpForm single-flight block.
    await fillOtp(user);

    await waitFor(() => {
      expect(verifyOtp).toHaveBeenCalledWith({
        phone: "+260971234567",
        token: "123456",
        type: "sms",
      });
      expect(getReadyCustomerSession).toHaveBeenCalledWith();
      expect(getPreferences).toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en");
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("retries failed post-auth reconciliation without consuming the OTP twice", async () => {
    verifyOtp.mockResolvedValue({ error: null });
    getReadyCustomerSession
      .mockRejectedValueOnce(new Error("merge failed"))
      .mockResolvedValueOnce({ access_token: "tok" });
    const user = userEvent.setup();

    render(
      <OtpForm
        locale="en"
        phone="+260971234567"
        labels={otpLabels}
        loginPath="/login"
        defaultNextPath="/en"
      />,
    );

    await fillOtp(user);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Generic error");
    });

    expect(verifyOtp).toHaveBeenCalledTimes(1);
    expect(getReadyCustomerSession).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(getReadyCustomerSession).toHaveBeenCalledTimes(2);
      expect(push).toHaveBeenCalledWith("/en");
    });
    expect(verifyOtp).toHaveBeenCalledTimes(1);
  });

  it("vendor OTP never calls customer preferences", async () => {
    verifyOtp.mockResolvedValue({ error: null });
    const user = userEvent.setup();

    render(
      <OtpForm
        locale="en"
        phone="+260971234567"
        labels={otpLabels}
        loginPath="/login"
        portal="vendor"
        defaultNextPath="/en"
        nextParam="/en/listings"
      />,
    );

    await fillOtp(user);

    await waitFor(() => {
      expect(verifyOtp).toHaveBeenCalled();
      expect(getReadyCustomerSession).not.toHaveBeenCalled();
      expect(getPreferences).not.toHaveBeenCalled();
      expect(push).toHaveBeenCalledWith("/en/listings");
    });
  });

  /**
   * Single-flight regression (Run #68).
   *
   * OtpForm has two verification triggers — OtpField's `onComplete` on the
   * sixth digit, and the Verify button — and its old guard was a `loading`
   * React state flag that only becomes true on the next render commit. A
   * redundant Verify interaction landing before that commit slipped through and
   * fired a SECOND verifyOtp for the same single-use code, which is what Run
   * #68's Vendor traces show as two POSTs to /auth/v1/verify.
   *
   * OtpForm is shared by both portals (apps/vendor/.../otp/page.tsx imports
   * this very component), so both are asserted.
   */
  describe("single-flight verification", () => {
    it("auto-submit plus a redundant Verify click sends exactly one verifyOtp (customer)", async () => {
      verifyOtp.mockResolvedValue({ error: null });
      const user = userEvent.setup();

      render(
        <OtpForm
          locale="en"
          phone="+260971234567"
          labels={otpLabels}
          loginPath="/login"
          defaultNextPath="/en"
        />,
      );

      await fillOtp(user);
      // Matches the submit control in EITHER state ("Verify" idle / "Verifying"
      // while a flight is held), so this fails on the call count below rather
      // than on a name lookup if the guard ever regresses.
      const submitButton = screen.getByRole("button", { name: /^verify/i });
      await user.click(submitButton).catch(() => undefined);

      await waitFor(() => {
        expect(push).toHaveBeenCalledWith("/en");
      });
      expect(verifyOtp).toHaveBeenCalledTimes(1);
    });

    it("auto-submit plus a redundant Verify click sends exactly one verifyOtp (vendor)", async () => {
      verifyOtp.mockResolvedValue({ error: null });
      const user = userEvent.setup();

      render(
        <OtpForm
          locale="en"
          phone="+260971234567"
          labels={otpLabels}
          loginPath="/login"
          portal="vendor"
          defaultNextPath="/en"
          nextParam="/en/listings"
        />,
      );

      await fillOtp(user);
      const submitButton = screen.getByRole("button", { name: /^verify/i });
      await user.click(submitButton).catch(() => undefined);

      await waitFor(() => {
        expect(push).toHaveBeenCalledWith("/en/listings");
      });
      expect(verifyOtp).toHaveBeenCalledTimes(1);
      expect(getPreferences).not.toHaveBeenCalled();
    });

    it("stays locked after a successful verify so the spent code cannot be resubmitted", async () => {
      verifyOtp.mockResolvedValue({ error: null });
      const user = userEvent.setup();

      render(
        <OtpForm
          locale="en"
          phone="+260971234567"
          labels={otpLabels}
          loginPath="/login"
          portal="vendor"
          defaultNextPath="/en"
        />,
      );

      await fillOtp(user);
      await waitFor(() => {
        expect(push).toHaveBeenCalled();
      });

      // Re-entering a digit must not re-arm submission: the code is consumed
      // and navigation is in flight, so a second verifyOtp could only fail.
      const group = screen.getByRole("group", { name: "Verification code" });
      const inputs = group.querySelectorAll("input");
      await user.type(inputs[5]!, "9").catch(() => undefined);

      expect(verifyOtp).toHaveBeenCalledTimes(1);
    });

    it("re-arms submission after a rejected code so the user can retry", async () => {
      verifyOtp.mockResolvedValue({ error: { message: "Invalid OTP" } });
      const user = userEvent.setup();

      render(
        <OtpForm
          locale="en"
          phone="+260971234567"
          labels={otpLabels}
          loginPath="/login"
          defaultNextPath="/en"
        />,
      );

      await fillOtp(user);
      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent("Wrong code");
      });
      expect(verifyOtp).toHaveBeenCalledTimes(1);

      // A rejection is recoverable — the lock must have been released.
      await user.click(screen.getByRole("button", { name: "Verify" }));

      await waitFor(() => {
        expect(verifyOtp).toHaveBeenCalledTimes(2);
      });
    });
  });
});

describe("ResendCountdown", () => {
  it("disables resend during cooldown then re-enables", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onResend = vi.fn().mockResolvedValue(undefined);

    render(
      <ResendCountdown
        cooldownSeconds={3}
        onResend={onResend}
        resendLabel="Resend code"
        resendInLabel="Resend in {seconds}s"
        loadingLabel="Loading"
      />,
    );

    const button = screen.getByRole("button", { name: "Resend in 3s" });
    expect(button).toBeDisabled();

    await vi.advanceTimersByTimeAsync(3000);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Resend code" })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: "Resend code" }));

    await waitFor(() => {
      expect(onResend).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "Resend in 3s" })).toBeDisabled();
    });
  });
});
