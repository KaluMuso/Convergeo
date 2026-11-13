// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepPayment, type PaymentStepLabels } from "./step-payment";

const requestMock = vi.fn();

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {},
  createApiClient: () => ({
    request: (...args: unknown[]) => requestMock(...args),
  }),
}));

const labels = new Proxy({} as Record<string, unknown>, {
  get: (_target, key: string) =>
    key === "codIneligible" ? (cap: string) => `codIneligible ${cap}` : `label:${key}`,
}) as unknown as PaymentStepLabels;

const totals = {
  session_id: "session-1",
  subtotal_ngwee: 20_000,
  delivery_fee_ngwee: 0,
  total_ngwee: 20_000,
  cod_cap_ngwee: 50_000,
};

function mockOptions(options: Record<string, unknown>) {
  requestMock.mockImplementation(async (path: string, init?: { method?: string }) => {
    if (String(path).includes("payment-options")) return { ...totals, ...options };
    if (init?.method === "POST") {
      const body = JSON.parse(String((init as { body?: string }).body)) as { method: string };
      return { ...totals, ...options, method: body.method, rail: null, payer_number: null };
    }
    throw new Error(`unexpected ${path}`);
  });
}

function renderStep(onComplete = vi.fn()) {
  render(
    <StepPayment
      locale="en"
      sessionId="session-1"
      accessToken="token"
      labels={labels}
      onComplete={onComplete}
    />,
  );
  return onComplete;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StepPayment honours the methods the API offers", () => {
  it("shows only cash on delivery, preselected, while online payments are off", async () => {
    mockOptions({ cod_eligible: true, available_methods: ["cod"] });
    const onComplete = renderStep();
    const user = userEvent.setup();

    const cod = await screen.findByLabelText("label:cod");
    expect(cod).toBeChecked();
    expect(screen.queryByRole("radio", { name: "label:momo" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("label:card")).not.toBeInTheDocument();
    // No mobile-money number form for a method that cannot be used.
    expect(screen.queryByLabelText("label:nationalNumber")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "label:continue" }));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(onComplete.mock.calls[0]?.[0]).toMatchObject({ method: "cod" });
  });

  it("says payment is unavailable instead of offering a dead end", async () => {
    // Over the COD cap with online payments off: nothing can be chosen.
    mockOptions({ cod_eligible: false, available_methods: [] });
    renderStep();

    expect(await screen.findByTestId("checkout-payments-off")).toHaveTextContent(
      "label:paymentsDisabled",
    );
    expect(screen.getByTestId("checkout-cod-unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "label:momo" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("label:card")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "label:continue" })).not.toBeInTheDocument();
  });

  it("offers every enabled method once online payments are on", async () => {
    mockOptions({ cod_eligible: true, available_methods: ["momo", "card", "cod"] });
    renderStep();

    expect(await screen.findByRole("radio", { name: "label:momo" })).toBeChecked();
    expect(screen.getByLabelText("label:card")).toBeInTheDocument();
    expect(screen.getByLabelText("label:cod")).toBeInTheDocument();
  });

  it("keeps the previous behaviour for an API that does not report methods", async () => {
    mockOptions({ cod_eligible: true });
    renderStep();

    expect(await screen.findByRole("radio", { name: "label:momo" })).toBeChecked();
    expect(screen.getByLabelText("label:card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "label:continue" })).toBeInTheDocument();
  });
});
