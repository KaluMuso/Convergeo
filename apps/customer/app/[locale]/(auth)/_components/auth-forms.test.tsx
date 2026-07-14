// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signInWithOtp = vi.fn();
const verifyOtp = vi.fn();
const exchangeCodeForSession = vi.fn();

vi.mock("@vergeo/auth/browser-client", () => ({
  createBrowserClient: () => ({
    auth: {
      signInWithOtp,
      verifyOtp,
      exchangeCodeForSession,
    },
  }),
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

    await fillOtp(user);
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(verifyOtp).toHaveBeenCalledWith({
        phone: "+260971234567",
        token: "123456",
        type: "sms",
      });
      expect(push).toHaveBeenCalledWith("/en");
      expect(refresh).toHaveBeenCalled();
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
