import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  getPaid: vi.fn(),
  query: "",
  paymentId: "20000000-0000-4000-8000-000000000002",
  auth: {
    session: { user: { id: "50000000-0000-4000-8000-000000000005" }, access_token: "token-a" },
    generation: 1,
    loading: false,
    error: null,
  },
}));
vi.mock("../../../../../../lib/customer-session", () => ({
  useSession: () => mocks.auth,
  customerAuth: { snapshot: () => mocks.auth },
}));
vi.mock("../../../../../../lib/api-base-url", () => ({
  resolveApiBaseUrl: () => "https://api.example.test",
  getApiBaseUrl: () => "https://api.example.test",
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "en", paymentId: mocks.paymentId }),
  useSearchParams: () => new URLSearchParams(mocks.query),
}));
vi.mock("next-intl", () => {
  const translate = (key: string) => key;
  return { useTranslations: () => translate };
});
vi.mock("@vergeo/config", () => ({
  ApiError: class extends Error {},
  createApiClient: ({ getToken }: { getToken: () => string | null }) => ({
    request: (path: string, options?: unknown) => mocks.request(path, options, getToken()),
  }),
}));

import { placeOrder } from "../../_lib/place-order";

import CardCheckoutPage from "./page";

// MOCKED-CONTRACT ONLY: API source 0ec0e2d4, tree ef1a5d14.
// These fixtures do not qualify API execution, PostgREST embedding or financial effects.
const jobId = "10000000-0000-4000-8000-000000000001";
const paymentId = mocks.paymentId;
const groupId = "30000000-0000-4000-8000-000000000003";
const orderId = "40000000-0000-4000-8000-000000000004";
const buyerId = "50000000-0000-4000-8000-000000000005";
const itemId = "60000000-0000-4000-8000-000000000006";
const listingId = "70000000-0000-4000-8000-000000000007";
const obligationId = "80000000-0000-4000-8000-000000000008";
const secondOrderId = "90000000-0000-4000-8000-000000000009";
const secondItemId = "a0000000-0000-4000-8000-00000000000a";
const common = {
  version: 1,
  buyer_id: buyerId,
  payment_id: paymentId,
  checkout_group_id: groupId,
  order_ids: [orderId],
  rail: "card",
  cod: false,
  amount_ngwee: 70000,
  currency: "ZMW",
};
const productLine = { order_item_id: itemId, item_kind: "product", listing_id: listingId };
const productContext = {
  ...common,
  kind: "product",
  orders: [{ order_id: orderId, lines: [productLine] }],
};
const serviceLink = {
  job_id: jobId,
  obligation_id: obligationId,
  leg: "balance",
  order_id: orderId,
  obligation_amount_ngwee: 70000,
  current_payment_id: paymentId,
};
const serviceContext = { ...common, kind: "service", service: serviceLink };
const ticketLine = {
  order_item_id: itemId,
  ticket_type_id: listingId,
  instance_id: jobId,
  qty: 1,
  unit_price_ngwee: 25000,
};
const ticketContext = {
  ...common,
  kind: "ticket",
  amount_ngwee: 26250,
  ticket: { order_id: orderId, lines: [ticketLine] },
};
function paymentStatus(context: unknown = serviceContext, overrides: Record<string, unknown> = {}) {
  return {
    payment_id: paymentId,
    checkout_group_id: groupId,
    order_id: orderId,
    amount_ngwee:
      typeof context === "object" && context !== null && "amount_ngwee" in context
        ? context.amount_ngwee
        : 70000,
    rail: "card",
    cod: false,
    status: "initiated",
    checkout_context: context,
    ...overrides,
  };
}
const verified = {
  payment_id: paymentId,
  checkout_group_id: groupId,
  status: "success",
  verified: true,
  order_confirmed: true,
};
const widgetSession = {
  payment_id: paymentId,
  checkout_group_id: groupId,
  amount_ngwee: 70000,
  amount_major: "700.00",
  currency: "ZMW",
  reference: "attempt-a",
  service_job_id: jobId,
  widget_script_url: "https://widget.example.test/card.js",
  customer: {
    email: "buyer@example.test",
    first_name: "Test",
    last_name: "Buyer",
    phone: "0971111111",
  },
};
function sessionFor(context: typeof common & { kind: string }) {
  return {
    ...widgetSession,
    amount_ngwee: context.amount_ngwee,
    amount_major: context.kind === "ticket" ? "262.50" : "700.00",
    service_job_id: context.kind === "service" ? jobId : null,
  };
}
function endpoints(
  payment: unknown = paymentStatus(),
  outcome: unknown = verified,
  session: unknown = widgetSession,
) {
  mocks.request.mockImplementation(async (path: string) => {
    if (path === `/payments/status?payment=${paymentId}`) return payment;
    if (path === `/payments/card/${paymentId}/verify`) return outcome;
    if (path === `/payments/card/${paymentId}/session`) return session;
    throw new Error(`Unexpected endpoint: ${path}`);
  });
}
const paths = () => mocks.request.mock.calls.map(([path]) => path);
const mutations = () =>
  mocks.request.mock.calls.filter(
    ([path, options]) => options?.method === "POST" || String(path).endsWith("/session"),
  );
const expectState = async (state: string) =>
  waitFor(() => expect(screen.getByTestId(`payment-card-${state}`)).toBeTruthy());
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}
beforeEach(() => {
  mocks.query = `job=${jobId}&status=success`;
  endpoints();
  vi.stubEnv("NEXT_PUBLIC_LENCO_PUBLIC_KEY", "test-public-key");
  window.LencoPay = { getPaid: mocks.getPaid };
  const script = document.createElement("script");
  script.src = widgetSession.widget_script_url;
  document.body.appendChild(script);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.unstubAllEnvs();
  document.querySelectorAll("script").forEach((script) => script.remove());
  delete window.LencoPay;
  mocks.auth.generation = 1;
  mocks.auth.loading = false;
  mocks.auth.session = { user: { id: buyerId }, access_token: "token-a" };
  mocks.paymentId = paymentId;
});

it("opens the actual product placeOrder navigation without caller hints", async () => {
  mocks.request.mockImplementation(async (path: string) => {
    if (path === "/orders") return { checkout_group_id: groupId };
    if (path === "/payments/card/session")
      return { payment_id: paymentId, checkout_group_id: groupId };
    if (path === `/payments/status?payment=${paymentId}`) return paymentStatus(productContext);
    if (path === `/payments/card/${paymentId}/session`) return sessionFor(productContext);
    throw new Error(`Unexpected product endpoint: ${path}`);
  });
  const navigate = vi.fn();
  await placeOrder({
    locale: "en",
    accessToken: "token-a",
    apiBaseUrl: "https://api.example.test",
    sessionId: groupId,
    payment: { method: "card", rail: null, payer_number: null },
    groups: [],
    idempotencyKey: "test-product-order",
    navigate,
  });
  expect(navigate).toHaveBeenCalledWith(`/en/checkout/card/${paymentId}`);
  mocks.query = new URL(
    navigate.mock.calls[0]![0],
    "https://customer.example.test",
  ).searchParams.toString();
  render(<CardCheckoutPage />);
  await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
  expect(paths()).toEqual([
    "/orders",
    "/payments/card/session",
    `/payments/status?payment=${paymentId}`,
    `/payments/card/${paymentId}/session`,
  ]);
});
it.each(["success", "failed"])(
  "restores the actual product %s return without caller hints",
  async (outcome) => {
    mocks.query = `status=${outcome}`;
    endpoints(paymentStatus(productContext), {
      ...verified,
      status: outcome,
      order_confirmed: outcome === "success",
    });
    render(<CardCheckoutPage />);
    await expectState(outcome);
    expect(paths()).toEqual([
      `/payments/status?payment=${paymentId}`,
      `/payments/card/${paymentId}/verify`,
    ]);
    expect(mocks.getPaid).not.toHaveBeenCalled();
    if (outcome === "success")
      expect(screen.getByRole("link", { name: "viewOrders" }).getAttribute("href")).toBe(
        "/en/account/orders",
      );
  },
);
it("accepts all vendor orders and optional canonical product IDs from a product union", async () => {
  mocks.query = `group=${groupId}&status=success`;
  endpoints(
    paymentStatus(
      {
        ...productContext,
        order_ids: [orderId, secondOrderId],
        orders: [
          ...productContext.orders,
          {
            order_id: secondOrderId,
            lines: [{ ...productLine, order_item_id: secondItemId, product_id: jobId }],
          },
        ],
      },
      { order_id: secondOrderId },
    ),
  );
  render(<CardCheckoutPage />);
  await expectState("success");
  expect(screen.queryByRole("link", { name: "backToJob" })).toBeNull();
});
it.each(["deposit", "balance"])(
  "restores service %s from the exact union on full reload",
  async (leg) => {
    // A balance payment's group differs from its original order's deposit group.
    endpoints(paymentStatus({ ...serviceContext, service: { ...serviceLink, leg } }));
    render(<CardCheckoutPage />);
    await expectState("success");
    expect(screen.getByRole("link", { name: "backToJob" }).getAttribute("href")).toBe(
      `/en/account/jobs/${jobId}`,
    );
    expect(paths()).toEqual([
      `/payments/status?payment=${paymentId}`,
      `/payments/card/${paymentId}/verify`,
    ]);
    expect(screen.queryByText("successBody")).toBeNull();
    expect(screen.getByText("status.success")).toBeTruthy();
    expect(mocks.getPaid).not.toHaveBeenCalled();
  },
);
it.each(["", `group=${groupId}`, `job=${jobId}&group=${groupId}`])(
  "classifies an unhinted/group-hinted service from the server (%s)",
  async (hint) => {
    mocks.query = `${hint}${hint ? "&" : ""}status=success`;
    render(<CardCheckoutPage />);
    await expectState("success");
    expect(screen.getByRole("link", { name: "backToJob" })).toBeTruthy();
  },
);
it("keeps a failed service attempt retry on the validated job", async () => {
  mocks.query = `job=${jobId}&status=failed`;
  endpoints(paymentStatus(), { ...verified, status: "failed", order_confirmed: false });
  render(<CardCheckoutPage />);
  await expectState("failed");
  expect(screen.getByRole("link", { name: "retryPayment" }).getAttribute("href")).toBe(
    `/en/account/jobs/${jobId}`,
  );
  expect(paths().some((path) => String(path).endsWith("/session"))).toBe(false);
});
it.each([false, true])(
  "opens a fee-bearing ticket with group hint=%s using the full charge",
  async (hinted) => {
    mocks.query = hinted ? `group=${groupId}` : "";
    endpoints(paymentStatus(ticketContext), verified, sessionFor(ticketContext));
    render(<CardCheckoutPage />);
    await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
    expect(mocks.getPaid.mock.calls[0]![0]).toMatchObject({ amount: "262.50", currency: "ZMW" });
    expect(paths()).toEqual([
      `/payments/status?payment=${paymentId}`,
      `/payments/card/${paymentId}/session`,
    ]);
  },
);
it.each(["success", "failed"])(
  "restores a fee-bearing ticket %s return and destination",
  async (outcome) => {
    mocks.query = `group=${groupId}&status=${outcome}`;
    endpoints(paymentStatus(ticketContext), {
      ...verified,
      status: outcome,
      order_confirmed: outcome === "success",
    });
    render(<CardCheckoutPage />);
    await expectState(outcome);
    expect(
      screen
        .getByRole("link", { name: outcome === "success" ? "viewOrders" : "retryPayment" })
        .getAttribute("href"),
    ).toBe(outcome === "success" ? "/en/account/orders" : `/en/checkout?group=${groupId}&retry=1`);
    expect(paths()).toEqual([
      `/payments/status?payment=${paymentId}`,
      `/payments/card/${paymentId}/verify`,
    ]);
    expect(mocks.getPaid).not.toHaveBeenCalled();
  },
);
it.each([productContext, serviceContext, ticketContext])(
  "does not declare confirmation from client success/context kind=$kind",
  async (context) => {
    mocks.query = "status=success";
    endpoints(paymentStatus(context), { ...verified, order_confirmed: false });
    render(<CardCheckoutPage />);
    await expectState("pending");
    expect(screen.queryByTestId("payment-card-success")).toBeNull();
  },
);
const invalidCommon: [string, unknown][] = [
  ["missing projection", paymentStatus(undefined, { checkout_context: undefined })],
  ["null projection", paymentStatus(null)],
  ["array projection", paymentStatus([])],
  ["unversioned projection", paymentStatus({ ...productContext, version: undefined })],
  ["future version", paymentStatus({ ...productContext, version: 2 })],
  ["unknown domain", paymentStatus({ ...productContext, kind: "unknown" })],
  ["foreign buyer", paymentStatus({ ...productContext, buyer_id: jobId })],
  ["invalid buyer", paymentStatus({ ...productContext, buyer_id: "buyer-a" })],
  ["foreign projected payment", paymentStatus({ ...productContext, payment_id: groupId })],
  ["foreign top payment", paymentStatus(productContext, { payment_id: groupId })],
  ["foreign group", paymentStatus(productContext, { checkout_group_id: orderId })],
  [
    "invalid group",
    paymentStatus(
      { ...productContext, checkout_group_id: "invalid" },
      { checkout_group_id: "invalid" },
    ),
  ],
  ["foreign top order", paymentStatus(productContext, { order_id: groupId })],
  ["missing top order", paymentStatus(productContext, { order_id: undefined })],
  ["empty membership", paymentStatus({ ...productContext, order_ids: [] })],
  ["duplicate membership", paymentStatus({ ...productContext, order_ids: [orderId, orderId] })],
  ["invalid membership", paymentStatus({ ...productContext, order_ids: [orderId, "not-an-id"] })],
  ["non-array membership", paymentStatus({ ...productContext, order_ids: orderId })],
  ["projected wrong rail", paymentStatus({ ...productContext, rail: "mtn" })],
  ["top wrong rail", paymentStatus(productContext, { rail: "mtn" })],
  ["projected COD", paymentStatus({ ...productContext, cod: true })],
  ["top COD", paymentStatus(productContext, { cod: true })],
  ["missing COD", paymentStatus({ ...productContext, cod: undefined })],
  ["foreign currency", paymentStatus({ ...productContext, currency: "USD" })],
  ["missing currency", paymentStatus({ ...productContext, currency: undefined })],
  ["mismatched amount", paymentStatus(productContext, { amount_ngwee: 70001 })],
  ...[0, -1, 7.5, Number.MAX_SAFE_INTEGER + 1, "70000", null].map((amount): [string, unknown] => [
    `unsafe amount ${String(amount)}`,
    paymentStatus({ ...productContext, amount_ngwee: amount }),
  ]),
];
const invalidDomains: [string, unknown][] = [
  ["product missing orders", { ...productContext, orders: undefined }],
  ["product empty orders", { ...productContext, orders: [] }],
  ["product mixed service", { ...productContext, service: serviceLink }],
  ["product mixed ticket", { ...productContext, ticket: ticketContext.ticket }],
  [
    "product foreign order",
    { ...productContext, orders: [{ order_id: groupId, lines: [productLine] }] },
  ],
  ["product missing vendor order", { ...productContext, order_ids: [orderId, secondOrderId] }],
  [
    "product duplicate order",
    {
      ...productContext,
      order_ids: [orderId, secondOrderId],
      orders: [productContext.orders[0], productContext.orders[0]],
    },
  ],
  ["product empty lines", { ...productContext, orders: [{ order_id: orderId, lines: [] }] }],
  [
    "product duplicate items",
    { ...productContext, orders: [{ order_id: orderId, lines: [productLine, productLine] }] },
  ],
  ...[
    { order_item_id: "invalid" },
    { item_kind: "ticket" },
    { listing_id: null },
    { product_id: null },
  ].map((line): [string, unknown] => [
    `invalid product line ${JSON.stringify(line)}`,
    { ...productContext, orders: [{ order_id: orderId, lines: [{ ...productLine, ...line }] }] },
  ]),
  ["service missing link", { ...serviceContext, service: null }],
  ["service mixed orders", { ...serviceContext, orders: productContext.orders }],
  ["service mixed ticket", { ...serviceContext, ticket: ticketContext.ticket }],
  ["service multiple orders", { ...serviceContext, order_ids: [orderId, secondOrderId] }],
  ...[
    { job_id: "invalid" },
    { obligation_id: "" },
    { leg: "product" },
    { leg: ["balance"] },
    { order_id: groupId },
    { obligation_amount_ngwee: 70001 },
    { current_payment_id: groupId },
  ].map((link): [string, unknown] => [
    `invalid/stale service ${JSON.stringify(link)}`,
    { ...serviceContext, service: { ...serviceLink, ...link } },
  ]),
  ["ticket missing link", { ...ticketContext, ticket: null }],
  ["ticket mixed service", { ...ticketContext, service: serviceLink }],
  ["ticket mixed orders", { ...ticketContext, orders: productContext.orders }],
  ["ticket multiple orders", { ...ticketContext, order_ids: [orderId, secondOrderId] }],
  [
    "ticket foreign order",
    { ...ticketContext, ticket: { order_id: groupId, lines: [ticketLine] } },
  ],
  ["ticket empty lines", { ...ticketContext, ticket: { order_id: orderId, lines: [] } }],
  [
    "ticket duplicate lines",
    { ...ticketContext, ticket: { order_id: orderId, lines: [ticketLine, ticketLine] } },
  ],
  ...[
    { order_item_id: null },
    { ticket_type_id: "invalid" },
    { instance_id: "invalid" },
    { qty: 0 },
    { qty: 1.5 },
    { qty: Number.MAX_SAFE_INTEGER + 1 },
    { unit_price_ngwee: 0 },
    { unit_price_ngwee: 1.5 },
    { unit_price_ngwee: Number.MAX_SAFE_INTEGER + 1 },
  ].map((line): [string, unknown] => [
    `invalid ticket line ${JSON.stringify(line)}`,
    { ...ticketContext, ticket: { order_id: orderId, lines: [{ ...ticketLine, ...line }] } },
  ]),
];
it.each([
  ...invalidCommon,
  ...invalidDomains.map(([name, context]): [string, unknown] => [name, paymentStatus(context)]),
])("rejects %s before entry resume or return verification", async (_name, payment) => {
  endpoints(payment);
  for (const query of ["", "status=success"]) {
    mocks.query = query;
    const view = render(<CardCheckoutPage />);
    await expectState("error");
    expect(mutations()).toHaveLength(0);
    expect(mocks.getPaid).not.toHaveBeenCalled();
    expect(screen.queryByRole("link")).toBeNull();
    view.unmount();
  }
});
it.each([
  "job=",
  "job=service-prefix",
  `job=${jobId}&job=${jobId}`,
  `job=${groupId}`,
  "group=",
  "group=invalid",
  `group=${groupId}&group=${groupId}`,
  `group=${orderId}`,
  "status=unknown",
  "status=success&status=success",
  "session=legacy",
  "kind=product",
])("rejects invalid/repeated/inconsistent hints %s", async (query) => {
  mocks.query = query;
  render(<CardCheckoutPage />);
  await expectState("error");
  expect(mutations()).toHaveLength(0);
});
it.each([productContext, ticketContext])(
  "does not let a job hint reclassify kind=$kind",
  async (context) => {
    endpoints(paymentStatus(context));
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(mutations()).toHaveLength(0);
  },
);
it.each([403, 404, 410, 503])(
  "fails closed on foreign/missing/expired/unavailable context (%s)",
  async (code) => {
    mocks.request.mockRejectedValue(new Error(String(code)));
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(mutations()).toHaveLength(0);
  },
);
it("rejects an invalid payment reference before any request", async () => {
  mocks.paymentId = "invalid";
  render(<CardCheckoutPage />);
  await expectState("error");
  expect(mocks.request).not.toHaveBeenCalled();
});
it.each([productContext, serviceContext, ticketContext])(
  "resumes kind=$kind once in StrictMode and verifies duplicate callbacks once",
  async (context) => {
    mocks.query = "";
    endpoints(paymentStatus(context), verified, sessionFor(context));
    render(
      <StrictMode>
        <CardCheckoutPage />
      </StrictMode>,
    );
    await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
    expect(paths().filter((path) => String(path).endsWith("/session"))).toHaveLength(1);
    const config = mocks.getPaid.mock.calls[0]![0];
    await act(async () => {
      config.onSuccess({ reference: "attempt-a" });
      config.onClose();
      config.onSuccess({ reference: "attempt-a" });
    });
    await expectState("success");
    expect(paths().filter((path) => String(path).endsWith("/verify"))).toHaveLength(1);
    expect(paths()).not.toContain("/payments/card/session");
  },
);
it.each([productContext, serviceContext, ticketContext])(
  "revalidates duplicate kind=$kind return mounts without resuming",
  async (context) => {
    mocks.query = "status=success";
    endpoints(paymentStatus(context));
    const view = render(<CardCheckoutPage />);
    await expectState("success");
    view.unmount();
    render(<CardCheckoutPage />);
    await expectState("success");
    expect(paths().filter((path) => String(path).endsWith("/verify"))).toHaveLength(2);
    expect(paths().some((path) => String(path).endsWith("/session"))).toBe(false);
  },
);
it("uses a refreshed same-account token for verify without restarting context resolution", async () => {
  const read = deferred<ReturnType<typeof paymentStatus>>();
  mocks.request.mockImplementation((path: string) =>
    path.includes("/status?") ? read.promise : Promise.resolve(verified),
  );
  const view = render(<CardCheckoutPage />);
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
  mocks.auth.session = { ...mocks.auth.session, access_token: "token-refreshed" };
  view.rerender(<CardCheckoutPage />);
  await act(async () => read.resolve(paymentStatus()));
  await expectState("success");
  expect(mocks.request.mock.calls.map(([path, , token]) => [path, token])).toEqual([
    [`/payments/status?payment=${paymentId}`, "token-a"],
    [`/payments/card/${paymentId}/verify`, "token-refreshed"],
  ]);
});
it("suppresses stale ABA context before any mutation", async () => {
  const read = deferred<ReturnType<typeof paymentStatus>>();
  mocks.request.mockReturnValueOnce(read.promise).mockReturnValue(new Promise(() => {}));
  const view = render(<CardCheckoutPage />);
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
  mocks.auth.generation = 3;
  view.rerender(<CardCheckoutPage />);
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(2));
  await act(async () => read.resolve(paymentStatus()));
  expect(paths().every((path) => String(path).includes("/status?"))).toBe(true);
  expect(mutations()).toHaveLength(0);
});
it("does not resume after the buyer changes during context retrieval", async () => {
  const read = deferred<ReturnType<typeof paymentStatus>>();
  mocks.query = "";
  mocks.request.mockReturnValue(read.promise);
  render(<CardCheckoutPage />);
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
  mocks.auth.session = { user: { id: jobId }, access_token: "token-foreign" };
  await act(async () => read.resolve(paymentStatus()));
  expect(mutations()).toHaveLength(0);
  expect(mocks.getPaid).not.toHaveBeenCalled();
});
it("waits for authenticated session hydration before reading the union", async () => {
  mocks.auth.loading = true;
  const view = render(<CardCheckoutPage />);
  expect(mocks.request).not.toHaveBeenCalled();
  mocks.auth.loading = false;
  view.rerender(<CardCheckoutPage />);
  await expectState("success");
});
it.each([
  { payment_id: groupId },
  { checkout_group_id: orderId },
  { service_job_id: groupId },
  { service_job_id: null },
  { amount_ngwee: 70001 },
  { amount_major: "700.01" },
  { amount_major: "7e2" },
  { currency: "USD" },
])("rejects a mismatched service widget session %j", async (mismatch) => {
  mocks.query = `job=${jobId}`;
  endpoints(paymentStatus(), verified, { ...widgetSession, ...mismatch });
  render(<CardCheckoutPage />);
  await expectState("error");
  expect(mocks.getPaid).not.toHaveBeenCalled();
  expect(paths().some((path) => String(path).endsWith("/verify"))).toBe(false);
});
it.each([productContext, ticketContext])(
  "rejects an unexpected service job on kind=$kind session",
  async (context) => {
    mocks.query = "";
    endpoints(paymentStatus(context), verified, { ...sessionFor(context), service_job_id: jobId });
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(mocks.getPaid).not.toHaveBeenCalled();
  },
);
it.each([{ payment_id: groupId }, { checkout_group_id: orderId }])(
  "rejects a mismatched verify response %j",
  async (mismatch) => {
    endpoints(paymentStatus(), { ...verified, ...mismatch });
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(screen.queryByTestId("payment-card-success")).toBeNull();
  },
);
it("ignores verification completed after the auth generation changes", async () => {
  const old = deferred<typeof verified>();
  let verifications = 0;
  mocks.request.mockImplementation(async (path: string) => {
    if (path.includes("/status?")) return paymentStatus();
    if (path.endsWith("/verify"))
      return ++verifications === 1 ? old.promise : new Promise(() => {});
    throw new Error("Unexpected stale verification endpoint");
  });
  const view = render(<CardCheckoutPage />);
  await waitFor(() => expect(verifications).toBe(1));
  mocks.auth.generation = 3;
  view.rerender(<CardCheckoutPage />);
  await waitFor(() => expect(verifications).toBe(2));
  await act(async () => old.resolve(verified));
  await expectState("verifying");
  expect(screen.queryByTestId("payment-card-success")).toBeNull();
});
it.each([productContext, serviceContext, ticketContext])(
  "does not verify a late kind=$kind callback after auth changes",
  async (context) => {
    mocks.query = "";
    endpoints(paymentStatus(context), verified, sessionFor(context));
    render(<CardCheckoutPage />);
    await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
    const callback = mocks.getPaid.mock.calls[0]![0].onSuccess;
    mocks.auth.generation = 3;
    await act(async () => callback({ reference: widgetSession.reference }));
    expect(paths().some((path) => String(path).endsWith("/verify"))).toBe(false);
  },
);
it("does not open a widget when resume finishes after an auth-generation change", async () => {
  mocks.query = "";
  const resume = deferred<typeof widgetSession>();
  mocks.request.mockImplementation((path: string) =>
    path.includes("/status?") ? Promise.resolve(paymentStatus()) : resume.promise,
  );
  render(<CardCheckoutPage />);
  await waitFor(() => expect(mutations()).toHaveLength(1));
  mocks.auth.generation = 3;
  await act(async () => resume.resolve(widgetSession));
  expect(mocks.getPaid).not.toHaveBeenCalled();
});

// Generated by the real API handler + PaymentStatusResponse.model_dump_json
// with synthetic CurrentUser/FakeSupabase dependencies under strict isolation.
// A source-hash guard makes stale serialized fixtures fail until regenerated.
// This bridge proves this response/consumer boundary, not provider, JWT or DB behavior.
type BridgePayment = {
  payment_id: string;
  checkout_group_id: string;
  order_id: string;
  amount_ngwee: number;
  status: string;
  checkout_context: {
    kind: string;
    buyer_id: string;
    order_ids: string[];
    service?: {
      job_id: string;
      obligation_id: string;
      leg: string;
      order_id: string;
      current_payment_id: string;
    };
    ticket?: { lines: { qty: number; unit_price_ngwee: number }[] };
  };
};
type SerializedBridge = {
  meta: {
    api_source_sha256: string;
    api_fixture_sha256: string;
    api_lock_sha256: string;
    case_count: number;
  };
  cases: Record<string, { http_status: number; body?: BridgePayment; error_code?: string }>;
};
const serializedApiBridge = JSON.parse(String.raw`{
  "meta": {
    "api_source_sha256": "5730e63ccfe893471f11907e750ffbe0caca04b67a6a9de4c7524a00b434be3d",
    "api_fixture_sha256": "969dd45ffd4bc7ab4d4609843b0857d995094192e57c646b8945028a8e652242",
    "api_lock_sha256": "620da4523e6c314424ccedac2b70a12ed61d0feb9ae3b7eeb745119bc1bbd32b",
    "generator": "real get_payment_status + PaymentStatusResponse.model_dump_json; fake service and current-user dependencies",
    "python": "3.12.14",
    "strict_guard_loaded": true,
    "provider_or_database_calls": 0,
    "case_count": 18
  },
  "cases": {
    "product": {
      "http_status": 200,
      "body": {
        "checkout_group_id": "30000000-0000-4000-8000-000000000003",
        "payment_id": "20000000-0000-4000-8000-000000000002",
        "status": "initiated",
        "amount_ngwee": 25000,
        "rail": "card",
        "cod": false,
        "order_id": "40000000-0000-4000-8000-000000000004",
        "payer_phone": "+260971234567",
        "checkout_context": {
          "version": 1,
          "buyer_id": "50000000-0000-4000-8000-000000000005",
          "payment_id": "20000000-0000-4000-8000-000000000002",
          "checkout_group_id": "30000000-0000-4000-8000-000000000003",
          "order_ids": [
            "40000000-0000-4000-8000-000000000004"
          ],
          "rail": "card",
          "cod": false,
          "amount_ngwee": 25000,
          "currency": "ZMW",
          "kind": "product",
          "orders": [
            {
              "order_id": "40000000-0000-4000-8000-000000000004",
              "lines": [
                {
                  "order_item_id": "21adc3bf-f9b4-5dde-8bc4-f89f0f674921",
                  "item_kind": "product",
                  "listing_id": "82b12f62-25a8-52b9-b1ff-918aca25a341",
                  "product_id": "ceacd9b3-e819-5234-a88c-38f1e27f0187"
                }
              ]
            }
          ]
        }
      }
    },
    "ticket": {
      "http_status": 200,
      "body": {
        "checkout_group_id": "30000000-0000-4000-8000-000000000003",
        "payment_id": "20000000-0000-4000-8000-000000000002",
        "status": "initiated",
        "amount_ngwee": 26250,
        "rail": "card",
        "cod": false,
        "order_id": "40000000-0000-4000-8000-000000000004",
        "payer_phone": "+260971234567",
        "checkout_context": {
          "version": 1,
          "buyer_id": "50000000-0000-4000-8000-000000000005",
          "payment_id": "20000000-0000-4000-8000-000000000002",
          "checkout_group_id": "30000000-0000-4000-8000-000000000003",
          "order_ids": [
            "40000000-0000-4000-8000-000000000004"
          ],
          "rail": "card",
          "cod": false,
          "amount_ngwee": 26250,
          "currency": "ZMW",
          "kind": "ticket",
          "ticket": {
            "order_id": "40000000-0000-4000-8000-000000000004",
            "lines": [
              {
                "order_item_id": "21adc3bf-f9b4-5dde-8bc4-f89f0f674921",
                "ticket_type_id": "fb068989-f107-5d77-b956-a6ef2f86b5f9",
                "instance_id": "aa2acb65-02ff-5a4e-90de-5f28970a2dab",
                "qty": 2,
                "unit_price_ngwee": 12500
              }
            ]
          }
        }
      }
    },
    "deposit": {
      "http_status": 200,
      "body": {
        "checkout_group_id": "30000000-0000-4000-8000-000000000003",
        "payment_id": "20000000-0000-4000-8000-000000000002",
        "status": "initiated",
        "amount_ngwee": 25000,
        "rail": "card",
        "cod": false,
        "order_id": "40000000-0000-4000-8000-000000000004",
        "payer_phone": "+260971234567",
        "checkout_context": {
          "version": 1,
          "buyer_id": "50000000-0000-4000-8000-000000000005",
          "payment_id": "20000000-0000-4000-8000-000000000002",
          "checkout_group_id": "30000000-0000-4000-8000-000000000003",
          "order_ids": [
            "40000000-0000-4000-8000-000000000004"
          ],
          "rail": "card",
          "cod": false,
          "amount_ngwee": 25000,
          "currency": "ZMW",
          "kind": "service",
          "service": {
            "job_id": "c156d591-53c1-5231-b627-ef35fd4849c6",
            "obligation_id": "51e3f012-83bf-5d17-8d1e-adab49f236e1",
            "leg": "deposit",
            "order_id": "40000000-0000-4000-8000-000000000004",
            "obligation_amount_ngwee": 25000,
            "current_payment_id": "20000000-0000-4000-8000-000000000002"
          }
        }
      }
    },
    "balance": {
      "http_status": 200,
      "body": {
        "checkout_group_id": "7f227c28-44b0-5f65-8df4-784f78bae2ef",
        "payment_id": "20000000-0000-4000-8000-000000000002",
        "status": "initiated",
        "amount_ngwee": 25000,
        "rail": "card",
        "cod": false,
        "order_id": "40000000-0000-4000-8000-000000000004",
        "payer_phone": "+260971234567",
        "checkout_context": {
          "version": 1,
          "buyer_id": "50000000-0000-4000-8000-000000000005",
          "payment_id": "20000000-0000-4000-8000-000000000002",
          "checkout_group_id": "7f227c28-44b0-5f65-8df4-784f78bae2ef",
          "order_ids": [
            "40000000-0000-4000-8000-000000000004"
          ],
          "rail": "card",
          "cod": false,
          "amount_ngwee": 25000,
          "currency": "ZMW",
          "kind": "service",
          "service": {
            "job_id": "c156d591-53c1-5231-b627-ef35fd4849c6",
            "obligation_id": "c5dd6e75-335c-58f9-a47d-4d99a49f164a",
            "leg": "balance",
            "order_id": "40000000-0000-4000-8000-000000000004",
            "obligation_amount_ngwee": 25000,
            "current_payment_id": "20000000-0000-4000-8000-000000000002"
          }
        }
      }
    },
    "foreign_buyer": {
      "http_status": 403,
      "error_code": "forbidden"
    },
    "foreign_order": {
      "http_status": 403,
      "error_code": "forbidden"
    },
    "conflicting_group": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "missing_payment": {
      "http_status": 404,
      "error_code": "not_found"
    },
    "missing_product_link": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "mixed_product_ticket": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "missing_obligation": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "ambiguous_obligation": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "wrong_leg": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "wrong_original_order": {
      "http_status": 404,
      "error_code": "orders.not_found"
    },
    "stale_service_attempt": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "fractional_charge": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    },
    "wrong_card_rail": {
      "http_status": 200,
      "body": {
        "checkout_group_id": "30000000-0000-4000-8000-000000000003",
        "payment_id": "20000000-0000-4000-8000-000000000002",
        "status": "initiated",
        "amount_ngwee": 25000,
        "rail": "mtn",
        "cod": false,
        "order_id": "40000000-0000-4000-8000-000000000004",
        "payer_phone": "+260971234567",
        "checkout_context": {
          "version": 1,
          "buyer_id": "50000000-0000-4000-8000-000000000005",
          "payment_id": "20000000-0000-4000-8000-000000000002",
          "checkout_group_id": "30000000-0000-4000-8000-000000000003",
          "order_ids": [
            "40000000-0000-4000-8000-000000000004"
          ],
          "rail": "mtn",
          "cod": false,
          "amount_ngwee": 25000,
          "currency": "ZMW",
          "kind": "product",
          "orders": [
            {
              "order_id": "40000000-0000-4000-8000-000000000004",
              "lines": [
                {
                  "order_item_id": "21adc3bf-f9b4-5dde-8bc4-f89f0f674921",
                  "item_kind": "product",
                  "listing_id": "82b12f62-25a8-52b9-b1ff-918aca25a341",
                  "product_id": "ceacd9b3-e819-5234-a88c-38f1e27f0187"
                }
              ]
            }
          ]
        }
      }
    },
    "wrong_service_amount": {
      "http_status": 409,
      "error_code": "payment.context_unavailable"
    }
  }
}`) as SerializedBridge;
function bridgePayment(name: string): BridgePayment {
  const entry = serializedApiBridge.cases[name]!;
  expect(entry.http_status).toBe(200);
  expect(entry.body).toBeDefined();
  return entry.body!;
}
function bridgeSession(payment: BridgePayment) {
  const digits = String(payment.amount_ngwee).padStart(3, "0");
  return {
    ...widgetSession,
    payment_id: payment.payment_id,
    checkout_group_id: payment.checkout_group_id,
    amount_ngwee: payment.amount_ngwee,
    amount_major: `${digits.slice(0, -2)}.${digits.slice(-2)}`,
    service_job_id: payment.checkout_context.service?.job_id ?? null,
  };
}
function bridgeEndpoints(name: string, result: "success" | "failed" = "success") {
  const payment = bridgePayment(name);
  mocks.request.mockImplementation(
    async (
      path: string,
      options: { method?: string; body?: string } | undefined,
      token: string,
    ) => {
      expect(token).toBe("token-a");
      if (path === `/payments/status?payment=${paymentId}`) {
        expect(options).toBeUndefined();
        return payment;
      }
      if (path === `/payments/card/${paymentId}/session`) {
        expect(options).toBeUndefined();
        return bridgeSession(payment);
      }
      if (path === `/payments/card/${paymentId}/verify`) {
        expect(options).toEqual({
          method: "POST",
          body: JSON.stringify({ client_status: result }),
        });
        return {
          ...verified,
          checkout_group_id: payment.checkout_group_id,
          status: result,
          order_confirmed: result === "success",
        };
      }
      throw new Error(`Unexpected bridge endpoint: ${path}`);
    },
  );
  return payment;
}

describe("actual FastAPI-model serialized response bridge (mocked dependencies only)", () => {
  it("binds generated payloads to the exact API source, fixture and frozen lock", () => {
    const apiRoot = resolve(process.cwd(), "../../services/api");
    for (const [path, expected] of [
      ["app/routers/payment_status.py", serializedApiBridge.meta.api_source_sha256],
      ["tests/test_payment_status.py", serializedApiBridge.meta.api_fixture_sha256],
      ["uv.lock", serializedApiBridge.meta.api_lock_sha256],
    ]) {
      expect(
        createHash("sha256")
          .update(readFileSync(resolve(apiRoot, path!)))
          .digest("hex"),
      ).toBe(expected);
    }
    expect(serializedApiBridge.meta.case_count).toBe(18);
    for (const name of ["product", "ticket", "deposit", "balance"])
      expect(bridgePayment(name).status).toBe("initiated");
  });

  it("continues the real unhinted product placeOrder navigation with the serialized API response", async () => {
    const payment = bridgePayment("product");
    mocks.request.mockImplementation(
      async (
        path: string,
        options: { method?: string; body?: string } | undefined,
        token: string,
      ) => {
        expect(token).toBe("token-a");
        if (path === "/orders") {
          expect(options?.method).toBe("POST");
          expect(JSON.parse(options!.body!)).toMatchObject({ method: "card", session_id: groupId });
          return { checkout_group_id: payment.checkout_group_id };
        }
        if (path === "/payments/card/session") {
          expect(options).toEqual({
            method: "POST",
            body: JSON.stringify({ checkout_group_id: payment.checkout_group_id }),
          });
          return { payment_id: paymentId, checkout_group_id: payment.checkout_group_id };
        }
        expect(options).toBeUndefined();
        if (path === `/payments/status?payment=${paymentId}`) return payment;
        if (path === `/payments/card/${paymentId}/session`) return bridgeSession(payment);
        throw new Error(`Unexpected product bridge endpoint: ${path}`);
      },
    );
    const navigate = vi.fn();
    await placeOrder({
      locale: "en",
      accessToken: "token-a",
      apiBaseUrl: "https://api.example.test",
      sessionId: groupId,
      payment: { method: "card", rail: null, payer_number: null },
      groups: [
        {
          vendor_id: listingId,
          fulfilment: "pickup",
          delivery_zone: null,
          delivery_fee_ngwee: 0,
          subtotal_ngwee: 25000,
        },
      ],
      idempotencyKey: "model-bridge-product",
      navigate,
    });
    expect(navigate).toHaveBeenCalledWith(`/en/checkout/card/${paymentId}`);
    mocks.query = new URL(
      navigate.mock.calls[0]![0],
      "https://customer.example.test",
    ).searchParams.toString();
    render(
      <StrictMode>
        <CardCheckoutPage />
      </StrictMode>,
    );
    await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
    expect(paths().filter((path) => path === "/payments/card/session")).toHaveLength(1);
    expect(paths().filter((path) => path === `/payments/card/${paymentId}/session`)).toHaveLength(
      1,
    );
    expect(mocks.getPaid.mock.calls[0]![0]).toMatchObject({ amount: "250.00", currency: "ZMW" });
  });

  it.each(["product", "ticket", "deposit", "balance"])(
    "resumes the serialized %s attempt once without a fresh initiation",
    async (name) => {
      mocks.query = "";
      const payment = bridgeEndpoints(name);
      render(
        <StrictMode>
          <CardCheckoutPage />
        </StrictMode>,
      );
      await waitFor(() => expect(mocks.getPaid).toHaveBeenCalledTimes(1));
      const widget = mocks.getPaid.mock.calls[0]![0];
      expect(widget.amount).toBe(bridgeSession(payment).amount_major);
      expect(paths().filter((path) => path === `/payments/card/${paymentId}/session`)).toHaveLength(
        1,
      );
      expect(paths()).not.toContain("/payments/card/session");
      await act(async () => {
        widget.onSuccess({ reference: "attempt-a" });
        widget.onClose();
        widget.onSuccess({ reference: "attempt-a" });
      });
      await expectState("success");
      expect(paths().filter((path) => path === `/payments/card/${paymentId}/verify`)).toHaveLength(
        1,
      );
      if (name === "ticket") {
        const line = payment.checkout_context.ticket!.lines[0]!;
        expect(line.qty * line.unit_price_ngwee).toBe(25000);
        expect(payment.amount_ngwee).toBe(26250);
        expect(widget.amount).toBe("262.50");
      }
    },
  );

  it.each(
    ["product", "ticket", "deposit", "balance"].flatMap((name) => [
      { name, result: "success" as const },
      { name, result: "failed" as const },
    ]),
  )("restores serialized $name on an independent full $result return", async ({ name, result }) => {
    mocks.query = `status=${result}`;
    const payment = bridgeEndpoints(name, result);
    render(<CardCheckoutPage />);
    await expectState(result);
    expect(paths()).toEqual([
      `/payments/status?payment=${paymentId}`,
      `/payments/card/${paymentId}/verify`,
    ]);
    expect(mocks.getPaid).not.toHaveBeenCalled();
    if (name === "deposit" || name === "balance") {
      const service = payment.checkout_context.service!;
      expect(service.leg).toBe(name);
      expect(service.current_payment_id).toBe(paymentId);
      expect(service.order_id).toBe(orderId);
      expect(service.obligation_id).toMatch(/^[0-9a-f-]{36}$/);
      expect(
        screen
          .getByRole("link", { name: result === "success" ? "backToJob" : "retryPayment" })
          .getAttribute("href"),
      ).toBe(`/en/account/jobs/${service.job_id}`);
      if (name === "balance") expect(payment.checkout_group_id).not.toBe(groupId);
    } else if (name === "ticket" && result === "failed") {
      expect(screen.getByRole("link", { name: "retryPayment" }).getAttribute("href")).toBe(
        `/en/checkout?group=${payment.checkout_group_id}&retry=1`,
      );
    }
  });

  it.each(
    Object.entries(serializedApiBridge.cases).filter(([, entry]) => entry.http_status !== 200),
  )("fails closed on the real handler's %s relationship rejection", async (_name, entry) => {
    mocks.request.mockImplementation(async (path: string, options: unknown, token: string) => {
      expect(path).toBe(`/payments/status?payment=${paymentId}`);
      expect(options).toBeUndefined();
      expect(token).toBe("token-a");
      throw new Error(`${entry.http_status}:${entry.error_code}`);
    });
    for (const query of ["", "status=success"]) {
      mocks.query = query;
      const view = render(<CardCheckoutPage />);
      await expectState("error");
      expect(mutations()).toHaveLength(0);
      expect(mocks.getPaid).not.toHaveBeenCalled();
      view.unmount();
    }
  });

  it("rejects an authoritative non-card projection before any resume or verify", async () => {
    mocks.query = "";
    bridgeEndpoints("wrong_card_rail");
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(mutations()).toHaveLength(0);
    expect(mocks.getPaid).not.toHaveBeenCalled();
  });

  it("rejects a serialized owner response when a different account mounts the route", async () => {
    mocks.query = "";
    bridgeEndpoints("product");
    mocks.auth.session = { user: { id: jobId }, access_token: "token-a" };
    render(<CardCheckoutPage />);
    await expectState("error");
    expect(mutations()).toHaveLength(0);
  });

  it("discards the actual serialized service response after an ABA auth change", async () => {
    const read = deferred<BridgePayment>();
    mocks.request.mockReturnValueOnce(read.promise).mockReturnValue(new Promise(() => {}));
    mocks.query = "";
    const view = render(<CardCheckoutPage />);
    await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
    mocks.auth.generation = 3;
    view.rerender(<CardCheckoutPage />);
    await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(2));
    await act(async () => read.resolve(bridgePayment("balance")));
    expect(mutations()).toHaveLength(0);
    expect(mocks.getPaid).not.toHaveBeenCalled();
  });
});
