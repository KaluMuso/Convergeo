import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/i18n", () => ({
  LOCALES: ["en"],
  loadNamespace: async (_locale: string, namespace: string) =>
    namespace === "events"
      ? { ticketPurchase: { loginRequired: "Sign in", payCta: "Get tickets" } }
      : {},
}));
vi.mock("next-intl", () => ({
  createTranslator:
    ({ messages, namespace }: { messages: Record<string, unknown>; namespace: string }) =>
    (key: string) =>
      key
        .split(".")
        .reduce<unknown>(
          (value, part) =>
            typeof value === "object" && value !== null
              ? (value as Record<string, unknown>)[part]
              : undefined,
          messages[namespace],
        ) ?? key,
}));
vi.mock("next-intl/server", () => ({ getMessages: async () => ({}), setRequestLocale: () => {} }));
vi.mock("./_components/step-fulfilment", () => ({ CheckoutShell: () => null }));
vi.mock("./_components/ticket-checkout", () => ({ TicketCheckout: () => null }));

import CheckoutPage from "./page";

describe("checkout route", () => {
  it("mounts ticket checkout for a group and preserves the product checkout without one", async () => {
    const ticket = await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({ group: "00000000-0000-4000-8000-000000000001" }),
    });
    const product = await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({}),
    });
    expect(
      (ticket as React.ReactElement<{ children: React.ReactElement }>).props.children.type,
    ).toHaveProperty("name", "TicketCheckout");
    expect(
      (
        ticket as React.ReactElement<{
          children: React.ReactElement<{ loginLabel: string; payLabel: string }>;
        }>
      ).props.children.props,
    ).toMatchObject({ loginLabel: "Sign in", payLabel: "Get tickets" });
    expect(
      (product as React.ReactElement<{ children: React.ReactElement }>).props.children.type,
    ).toHaveProperty("name", "CheckoutShell");
  });

  it("does not enter product checkout for an empty group", async () => {
    const page = await CheckoutPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({ group: "" }),
    });
    expect(
      (page as React.ReactElement<{ children: React.ReactElement }>).props.children.type,
    ).toHaveProperty("name", "TicketCheckout");
  });
});
