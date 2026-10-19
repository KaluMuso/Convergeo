import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@vergeo/i18n", () => ({ LOCALES: ["en"], loadNamespace: async () => ({}) }));
vi.mock("next-intl", () => ({ createTranslator: () => (key: string) => key }));
vi.mock("next-intl/server", () => ({ getMessages: async () => ({}), setRequestLocale: () => {} }));
vi.mock("../_components/step-fulfilment", () => ({
  CheckoutShell: () => <div data-testid="product-cart" />,
  ExistingCheckoutUnavailable: () => <div role="alert">Unavailable</div>,
}));
vi.mock("../_components/lazy-ticket-checkout", () => ({
  LazyTicketCheckout: ({ groupId }: { groupId: string | null }) => (
    <div data-testid="validated-ticket-candidate">{groupId}</div>
  ),
}));

import CheckoutPage from "../page";

afterEach(cleanup);

it.each([
  { session: "service-group", kind: "service_deposit" },
  { session: "unclassified-product-session" },
  { session: "" },
  { session: ["first", "second"] },
  { group: "ticket", session: "other" },
  { job: "unverified-job" },
  { kind: "product" },
])("does not create a product cart for an unresolved handoff %j", async (query) => {
  render(
    await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve(query),
    }),
  );
  expect(screen.queryByTestId("product-cart")).toBeNull();
  expect(screen.getByRole("alert")).toBeTruthy();
});

it("preserves the fresh product entry and the existing ticket validator", async () => {
  const product = render(
    await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({}),
    }),
  );
  expect(screen.getByTestId("product-cart")).toBeTruthy();
  product.unmount();
  render(
    await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({ group: "ticket-group" }),
    }),
  );
  expect(screen.getByTestId("validated-ticket-candidate").textContent).toBe("ticket-group");
});
