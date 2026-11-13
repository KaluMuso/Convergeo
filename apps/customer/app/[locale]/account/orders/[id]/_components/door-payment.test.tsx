// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DoorPaymentBlock, type DoorPaymentLabels } from "./door-payment";

import type { DoorPayment } from "../../_components/orders-api";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const labels: DoorPaymentLabels = {
  title: "Pay at the door",
  intro: (amount) => `Pay ${amount} by mobile money`,
  waitingRider: "Waiting for the rider",
  payNow: "Pay now on your phone",
  sending: "Sending…",
  otherNumber: "Pay from another number",
  phoneLabel: "MTN or Airtel number",
  phoneHelp: "The prompt goes to this number.",
  pending: "Check your phone and enter your PIN",
  checkStatus: "Check payment status",
  checking: "Checking…",
  failed: "The payment did not go through",
  attemptsLeft: (count) => `${count} tries left`,
  noAttemptsLeft: "No more tries",
  paid: "Paid",
  cash: (amount) => `Pay the rider ${amount} in cash`,
  errors: {
    invalidPhone: "Bad number",
    operatorUnsupported: "Use MTN or Airtel",
    inFlight: "Prompt already on your phone",
    generic: "Something went wrong",
  },
};

function door(overrides: Partial<DoorPayment> = {}): DoorPayment {
  return {
    enabled: true,
    state: "awaiting_payment",
    amount_ngwee: 45_000,
    arrived: true,
    settled_via: null,
    attempts_used: 0,
    attempts_allowed: 3,
    latest_failure_reason: null,
    can_request: true,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  refresh.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DoorPaymentBlock", () => {
  it("renders nothing while the flag is off", () => {
    const { container } = render(
      <DoorPaymentBlock
        orderId="o1"
        accessToken="t"
        initial={door({ enabled: false, state: "not_applicable" })}
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("waits for the rider before offering the button", () => {
    render(
      <DoorPaymentBlock
        orderId="o1"
        accessToken="t"
        initial={door({ state: "awaiting_arrival", arrived: false, can_request: false })}
        labels={labels}
      />,
    );
    expect(screen.getByText("Waiting for the rider")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pay now on your phone" })).toBeNull();
  });

  it("sends the prompt without an amount and shows the pending state", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(door({ state: "pending" })));
    vi.stubGlobal("fetch", fetchMock);
    render(<DoorPaymentBlock orderId="o1" accessToken="t" initial={door()} labels={labels} />);
    expect(screen.getByText("Pay K450.00 by mobile money")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pay now on your phone" }));
    await waitFor(() =>
      expect(screen.getByText("Check your phone and enter your PIN")).toBeInTheDocument(),
    );
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/account/orders/o1/door-payment");
    expect(JSON.parse(String(init.body))).toEqual({});
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes the page (to reveal the code) only once the API says paid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(door({ state: "paid", settled_via: "mobile_money" }))),
    );
    render(
      <DoorPaymentBlock
        orderId="o1"
        accessToken="t"
        initial={door({ state: "pending", can_request: false })}
        labels={labels}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Check payment status" }));
    await waitFor(() => expect(screen.getByText("Paid")).toBeInTheDocument());
    expect(refresh).toHaveBeenCalled();
  });

  it("maps a Zamtel number error to a readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            error: {
              code: "door_payment_operator_unsupported",
              message: "x",
              request_id: "r1",
            },
          },
          422,
        ),
      ),
    );
    render(<DoorPaymentBlock orderId="o1" accessToken="t" initial={door()} labels={labels} />);
    fireEvent.click(screen.getByRole("button", { name: "Pay from another number" }));
    fireEvent.change(screen.getByLabelText(/MTN or Airtel number/), {
      target: { value: "0991234567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Pay now on your phone" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Use MTN or Airtel"));
  });

  it("offers no retry when attempts are used up", () => {
    render(
      <DoorPaymentBlock
        orderId="o1"
        accessToken="t"
        initial={door({ state: "failed", attempts_used: 3, can_request: false })}
        labels={labels}
      />,
    );
    expect(screen.getByText("No more tries")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pay now on your phone" })).toBeNull();
  });
});
