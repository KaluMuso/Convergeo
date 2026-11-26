// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { contactRequest, FakeApiError } = vi.hoisted(() => {
  class FakeApiError extends Error {
    readonly code: string;
    constructor(code: string) {
      super(code);
      this.code = code;
    }
  }
  return { contactRequest: vi.fn(), FakeApiError };
});

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({ auth: {} }),
}));

vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ session: { access_token: "signed-in-token" }, loading: false }),
  reconcileCustomerSession: vi.fn(),
}));

vi.mock("@vergeo/config", () => ({
  ApiError: FakeApiError,
  createApiClient: () => ({ request: contactRequest }),
}));

import { StepContact, type ContactStepLabels } from "./step-contact";

const labels = {
  title: "Your contact details",
  subtitle: "Order updates",
  phoneLabel: "Phone number",
  phoneHelp: "Help",
  phonePlaceholder: "97X XXX XXX",
  countryCode: "Country code",
  nationalNumber: "Mobile number",
  sendOtp: "Send code",
  verifyOtp: "Verify",
  otpAria: "Code",
  otpDigit: "Digit {position} of {total}",
  resend: "Resend",
  resendIn: "Resend in {seconds}s",
  changePhone: "Change",
  loading: "Loading",
  required: "Required",
  invalidPhone: "Invalid phone",
  sendFailed: "Send failed",
  wrongCode: "Wrong code",
  expired: "Expired",
  throttled: "Wait {seconds}",
  generic: "Something went wrong",
  skippedLoggedIn: "Using your account phone number",
  needPhone: "Add your phone",
  savePhone: "Save and continue",
  saveFailed: "Could not continue",
} satisfies ContactStepLabels;

afterEach(() => {
  cleanup();
  contactRequest.mockReset();
});

describe("StepContact signed-in buyer", () => {
  it("skips straight on when the profile already has a phone", async () => {
    contactRequest.mockResolvedValue({ verified: true, skipped: true });
    const onComplete = vi.fn();
    render(<StepContact labels={labels} onComplete={onComplete} />);
    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
  });

  it("asks for a phone when the account has none, then saves it and continues", async () => {
    contactRequest
      .mockRejectedValueOnce(new FakeApiError("checkout.phone_required"))
      .mockResolvedValueOnce({ verified: true, skipped: false });
    const onComplete = vi.fn();
    const user = userEvent.setup();
    render(<StepContact labels={labels} onComplete={onComplete} />);

    await screen.findByTestId("checkout-contact-add-phone");
    expect(onComplete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: labels.savePhone }));
    expect(screen.getByText(labels.required)).toBeInTheDocument();

    await user.type(screen.getByLabelText(labels.nationalNumber), "971234567");
    await user.click(screen.getByRole("button", { name: labels.savePhone }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
    const [, init] = contactRequest.mock.calls[1] as [string, { body: string }];
    expect(JSON.parse(init.body)).toEqual({ phone: "+260971234567" });
  });

  it("shows an error with a retry button when the request fails for another reason", async () => {
    contactRequest
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ verified: true, skipped: true });
    const onComplete = vi.fn();
    const user = userEvent.setup();
    render(<StepContact labels={labels} onComplete={onComplete} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(labels.saveFailed);
    await user.click(screen.getByRole("button", { name: labels.savePhone }));
    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce());
  });
});
