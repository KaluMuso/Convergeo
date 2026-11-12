// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import type { CheckoutShellLabels } from "./step-fulfilment";

const mocks = vi.hoisted(() => ({
  authEvent: (_event: string, _session: unknown) => {},
  verify: vi.fn(),
  fetch: vi.fn(),
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      onAuthStateChange: (fn: typeof mocks.authEvent) => {
        mocks.authEvent = fn;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
      getSession: async () => ({ data: { session: null }, error: null }),
      signInWithOtp: async () => ({ error: null }),
      verifyOtp: mocks.verify,
    },
  }),
}));
const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const m = checkoutMessages.checkout;
const labels = {
  ...m,
  stepAnnouncementTemplate: m.stepAnnouncement,
  contact: {
    ...m.contact,
    otpDigitTemplate: m.contact.otpDigit,
    resendInTemplate: m.contact.resendIn,
    throttledTemplate: m.contact.throttled,
  },
  fulfilment: {
    ...m.fulfilment,
    zoneFeeTemplate: m.fulfilment.zoneFee,
    zoneLabelTemplate: m.fulfilment.zoneLabel,
    pickupAtTemplate: m.fulfilment.pickupAt,
    pickupHoursTemplate: m.fulfilment.pickupHours,
  },
  payment: { ...m.payment, codIneligibleTemplate: m.payment.codIneligible },
  review: {
    ...m.review,
    methodMomoTemplate: m.review.methodMomo,
    payerNumberTemplate: m.review.payerNumber,
  },
  countdown: { ...m.countdown, ariaLiveTemplate: m.countdown.ariaLive },
} as unknown as CheckoutShellLabels;
const account = {
  access_token: "fixture-token",
  user: { id: "fixture-account", phone: "+260971234567" },
};
const checkout = {
  session_id: "fixture-checkout",
  expires_at: new Date(Date.now() + 900000).toISOString(),
  reservation_ttl_min: 15,
  contact_skipped: false,
  subtotal_ngwee: 10000,
  vendor_groups: [
    {
      vendor_id: "fixture-vendor",
      vendor_name: "Fixture vendor",
      items: [],
      subtotal_ngwee: 10000,
      delivery_eligible: false,
      pickup_location: null,
    },
  ],
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
const failure = () =>
  json(
    {
      error: {
        code: "fixture.unavailable",
        message: "Synthetic unavailable",
        request_id: "fixture",
      },
    },
    503,
  );
let events: string[];
beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("fetch", mocks.fetch);
  mocks.fetch.mockReset();
  mocks.verify.mockReset();
  events = [];
  mocks.verify.mockImplementation(async () => {
    events.push("verify");
    mocks.authEvent("SIGNED_IN", account);
    return { data: { session: account }, error: null };
  });
  mocks.fetch.mockImplementation(async (url: string) => {
    const path = new URL(url, "http://localhost").pathname;
    events.push(path);
    if (path.endsWith("/steps/contact")) return json({ verified: true, skipped: false });
    if (path.endsWith("/checkout/session")) return json(checkout);
    return json({});
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function start() {
  const { CheckoutShell } = await import("./step-fulfilment");
  const user = userEvent.setup();
  const view = render(<CheckoutShell locale="en" labels={labels} />);
  await user.type(await screen.findByLabelText(m.contact.nationalNumber), "971234567");
  await user.click(screen.getByRole("button", { name: m.contact.sendOtp }));
  await user.click(screen.getByLabelText("Digit 1 of 6"));
  await user.keyboard("123456");
  return { user, view };
}

it("persists accepted contact before creating checkout across the real auth-store remount", async () => {
  await start();
  await screen.findByText("Fixture vendor");
  expect(events).toEqual(["verify", "/cart/merge", "/checkout/steps/contact", "/checkout/session"]);
  expect(screen.getAllByRole("radio")).toHaveLength(2);
  const contact = mocks.fetch.mock.calls.find(([url]) => String(url).endsWith("/steps/contact"));
  expect(JSON.parse(contact![1].body)).toEqual({ phone: account.user.phone });
  expect(mocks.verify).toHaveBeenCalledOnce();
});
it("shows merge failure and retries reconciliation without asking for a spent OTP", async () => {
  const normal = mocks.fetch.getMockImplementation()!;
  let failed = false;
  mocks.fetch.mockImplementation(async (url, init) => {
    if (String(url).endsWith("/cart/merge") && !failed) {
      failed = true;
      return failure();
    }
    return normal(url, init);
  });
  const { user } = await start();
  expect(await screen.findByRole("alert")).toHaveTextContent(m.error);
  expect(events).not.toContain("/checkout/session");
  await user.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("Fixture vendor");
  expect(mocks.verify).toHaveBeenCalledOnce();
});
it("keeps a failed session visible and permits an explicit single-flight retry", async () => {
  const normal = mocks.fetch.getMockImplementation()!;
  let failed = false;
  mocks.fetch.mockImplementation(async (url, init) => {
    if (String(url).endsWith("/checkout/session") && !failed) {
      failed = true;
      return failure();
    }
    return normal(url, init);
  });
  const { user } = await start();
  expect(await screen.findByRole("alert")).toHaveTextContent(m.error);
  await user.dblClick(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("Fixture vendor");
  expect(mocks.verify).toHaveBeenCalledOnce();
});
it("does not present an empty vendor response as usable fulfilment", async () => {
  const normal = mocks.fetch.getMockImplementation()!;
  mocks.fetch.mockImplementation(async (url, init) =>
    String(url).endsWith("/checkout/session")
      ? json({ ...checkout, vendor_groups: [] })
      : normal(url, init),
  );
  await start();
  expect(await screen.findByRole("alert")).toHaveTextContent(m.error);
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to cart" })).toHaveAttribute("href", "/en/cart");
});

for (const verified of [false, "error"]) {
  it(`does not open checkout after contact ${verified === false ? "is unverified" : "fails"}`, async () => {
    const normal = mocks.fetch.getMockImplementation()!;
    mocks.fetch.mockImplementation(async (url, init) =>
      String(url).endsWith("/steps/contact")
        ? verified === false
          ? json({ verified: false })
          : failure()
        : normal(url, init),
    );
    await start();
    expect(await screen.findByRole("alert")).toHaveTextContent(m.error);
    expect(mocks.fetch.mock.calls.some(([url]) => String(url).endsWith("/checkout/session"))).toBe(
      false,
    );
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
}

it("drops a late old-account contact response before requesting its checkout session", async () => {
  let finish!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const normal = mocks.fetch.getMockImplementation()!;
  mocks.fetch.mockImplementation(async (url, init) => {
    const token = new Headers(init?.headers).get("Authorization");
    if (String(url).endsWith("/steps/contact") && token === "Bearer fixture-token") return pending;
    return normal(url, init);
  });
  await start();
  await waitFor(() =>
    expect(mocks.fetch.mock.calls.some(([url]) => String(url).endsWith("/steps/contact"))).toBe(
      true,
    ),
  );
  await act(async () => {
    mocks.authEvent("SIGNED_OUT", null);
    mocks.authEvent("SIGNED_IN", {
      access_token: "fixture-token-b",
      user: { id: "account-b", phone: "+260971234568" },
    });
  });
  await screen.findByText("Fixture vendor");
  await act(async () => finish(json({ verified: true })));
  const sessions = mocks.fetch.mock.calls.filter(([url]) =>
    String(url).endsWith("/checkout/session"),
  );
  expect(sessions).toHaveLength(1);
  expect(new Headers(sessions[0]![1].headers).get("Authorization")).toBe("Bearer fixture-token-b");
});
