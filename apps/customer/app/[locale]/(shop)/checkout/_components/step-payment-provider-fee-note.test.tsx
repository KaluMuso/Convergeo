// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
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

const codGuide = new Proxy({} as Record<string, string>, {
  get: (_target, key: string) => `codGuide:${key}`,
});

function makeLabels(withFeeNote: boolean): PaymentStepLabels {
  return new Proxy({} as Record<string, unknown>, {
    get: (_target, key: string) => {
      if (key === "codIneligible")
        return (cap: string) => `codIneligible ${cap}`;
      if (key === "codGuide") return codGuide;
      if (key === "providerFeeNote" && !withFeeNote) return undefined;
      return `label:${key}`;
    },
  }) as unknown as PaymentStepLabels;
}

const options = {
  session_id: "session-1",
  subtotal_ngwee: 20_000,
  delivery_fee_ngwee: 0,
  total_ngwee: 20_000,
  cod_cap_ngwee: 50_000,
  cod_eligible: true,
  available_methods: ["momo", "card", "cod"],
};

function renderStep(withFeeNote = true) {
  requestMock.mockResolvedValue(options);
  render(
    <StepPayment
      locale="en"
      sessionId="session-1"
      accessToken="token"
      labels={makeLabels(withFeeNote)}
      onComplete={vi.fn()}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StepPayment provider fee note (bearer=customer)", () => {
  it("tells the payer the provider fee is added for mobile money and card, never cash", async () => {
    renderStep();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: "label:momo" }));
    expect(screen.getByTestId("checkout-provider-fee-note")).toHaveTextContent(
      "label:providerFeeNote",
    );

    await user.click(screen.getByRole("radio", { name: "label:cod" }));
    expect(
      screen.queryByTestId("checkout-provider-fee-note"),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "label:card" }));
    expect(
      screen.getByTestId("checkout-provider-fee-note"),
    ).toBeInTheDocument();
  });

  it("never invents a fee amount", async () => {
    renderStep();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "label:momo" }));
    expect(
      screen.getByTestId("checkout-provider-fee-note").textContent,
    ).not.toMatch(/K\s?\d/);
  });

  it("renders nothing when no label is supplied", async () => {
    renderStep(false);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "label:momo" }));
    expect(
      screen.queryByTestId("checkout-provider-fee-note"),
    ).not.toBeInTheDocument();
  });
});
