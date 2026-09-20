// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { signInWithOtp, verifyOtp, mergeGuestCartIntoAccount, contactRequest } = vi.hoisted(() => ({
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
  mergeGuestCartIntoAccount: vi.fn(),
  contactRequest: vi.fn(),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: { signInWithOtp, verifyOtp },
  }),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: null, loading: false }),
}));

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request: contactRequest }),
}));

vi.mock("../../../../../lib/cart-merge", () => ({
  mergeGuestCartIntoAccount,
}));

import { StepContact, type ContactStepLabels } from "./step-contact";

const labels: ContactStepLabels = {
  title: "Your contact details",
  subtitle: "Order updates",
  phoneLabel: "Mobile number",
  phoneHelp: "We will send a code",
  phonePlaceholder: "97X XXX XXX",
  countryCode: "Country code",
  nationalNumber: "Mobile number",
  sendOtp: "Send code",
  verifyOtp: "Verify & continue",
  otpAria: "Enter the 6-digit verification code",
  otpDigit: "Digit {position} of {total}",
  resend: "Resend code",
  resendIn: "Resend in {seconds}s",
  changePhone: "Change number",
  loading: "Loading",
  required: "Required",
  invalidPhone: "Invalid phone",
  sendFailed: "Send failed",
  wrongCode: "Wrong code",
  expired: "Expired",
  throttled: "Try again in {seconds} seconds",
  generic: "Something went wrong",
  skippedLoggedIn: "Already signed in",
};

async function submitOtp(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(labels.nationalNumber), "971234567");
  await user.click(screen.getByRole("button", { name: labels.sendOtp }));

  const group = await screen.findByRole("group", { name: labels.otpAria });
  const inputs = group.querySelectorAll("input");
  for (let index = 0; index < 6; index += 1) {
    await user.type(inputs[index]!, String(index + 1));
  }
}

beforeEach(() => {
  signInWithOtp.mockReset();
  verifyOtp.mockReset();
  mergeGuestCartIntoAccount.mockReset();
  contactRequest.mockReset();

  signInWithOtp.mockResolvedValue({ error: null });
  verifyOtp.mockResolvedValue({
    data: { session: { access_token: "real-session-token" } },
    error: null,
  });
  mergeGuestCartIntoAccount.mockResolvedValue(undefined);
  contactRequest.mockResolvedValue({ contact_skipped: false });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StepContact authenticated OTP ordering", () => {
  it("orders verify, cart merge, contact persistence, then Fulfilment", async () => {
    const events: string[] = [];
    verifyOtp.mockImplementation(async () => {
      events.push("verifyOtp");
      return {
        data: { session: { access_token: "real-session-token" } },
        error: null,
      };
    });
    mergeGuestCartIntoAccount.mockImplementation(async () => {
      events.push("cart merge");
    });
    contactRequest.mockImplementation(async () => {
      events.push("contact POST");
      return { contact_skipped: false };
    });
    const onComplete = vi.fn(() => events.push("onComplete"));
    const user = userEvent.setup();

    render(<StepContact labels={labels} onComplete={onComplete} />);
    await submitOtp(user);

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
    expect(events).toEqual(["verifyOtp", "cart merge", "contact POST", "onComplete"]);
    expect(mergeGuestCartIntoAccount).toHaveBeenCalledWith("real-session-token");
    expect(contactRequest).toHaveBeenCalledWith("/checkout/steps/contact", {
      method: "POST",
      body: JSON.stringify({ phone: "+260971234567" }),
    });
  });

  it("fails closed on merge and retries post-auth work without resubmitting the spent OTP", async () => {
    mergeGuestCartIntoAccount
      .mockRejectedValueOnce(new Error("merge failed"))
      .mockResolvedValueOnce(undefined);
    const onComplete = vi.fn();
    const user = userEvent.setup();

    render(<StepContact labels={labels} onComplete={onComplete} />);
    await submitOtp(user);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(labels.generic);
    });
    expect(verifyOtp).toHaveBeenCalledOnce();
    expect(contactRequest).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: labels.verifyOtp }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
    expect(verifyOtp).toHaveBeenCalledOnce();
    expect(mergeGuestCartIntoAccount).toHaveBeenCalledTimes(2);
    expect(contactRequest).toHaveBeenCalledOnce();
  });
});
