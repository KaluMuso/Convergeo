// @vitest-environment jsdom
/**
 * CUST-I18N-01 — Bemba/Nyanja rendering for critical purchase-journey surfaces.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { formatK } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import bemCatalog from "../../../../../../packages/i18n/messages/bem/catalog.json";
import bemCheckout from "../../../../../../packages/i18n/messages/bem/checkout.json";
import nyaCatalog from "../../../../../../packages/i18n/messages/nya/catalog.json";
import nyaCheckout from "../../../../../../packages/i18n/messages/nya/checkout.json";

import { HomeTrustStrip } from "./home-trust-strip";

afterEach(() => {
  cleanup();
});

function trustLabels(messages: typeof bemCatalog, locale: string) {
  const t = createTranslator({
    locale,
    messages: { catalog: messages },
    namespace: "catalog",
  });
  return {
    ariaLabel: t("home.trust.ariaLabel"),
    sellers: t("home.trust.sellers"),
    fulfillment: t("home.trust.fulfillment"),
    returns: t("home.trust.returns"),
    escrow: t("home.trust.escrow"),
  };
}

describe("Phase-1 bem/nya homepage trust + hero escrow", () => {
  it.each([
    ["bem", bemCatalog],
    ["nya", nyaCatalog],
  ] as const)("%s trust strip uses vernacular (not English)", (locale, messages) => {
    render(<HomeTrustStrip labels={trustLabels(messages, locale)} />);
    expect(screen.getByTestId("home-trust-escrow")).toHaveTextContent(messages.home.trust.escrow);
    expect(screen.getByTestId("home-trust-escrow")).not.toHaveTextContent(
      "When online payment is available",
    );
    expect(messages.home.hero.escrowStep1).not.toBe("You pay");
    expect(messages.home.hero.escrowStep2).toContain("Vergeo5");
    expect(messages.home.hero.escrowStep3).not.toBe("Released on delivery");
  });
});

describe("Phase-1 bem/nya PDP purchase copy", () => {
  it.each([
    ["bem", bemCatalog],
    ["nya", nyaCatalog],
  ] as const)("%s buy-box / seller / returns / escrow strings resolve", (locale, messages) => {
    const t = createTranslator({
      locale,
      messages: { catalog: messages },
      namespace: "catalog",
    });
    expect(t("pdp.buyBox.addToCart")).toBe(messages.pdp.buyBox.addToCart);
    expect(t("pdp.buyBox.addToCart")).not.toBe("Add to cart");
    expect(t("pdp.buyBox.quantityLabel")).toBe(messages.pdp.buyBox.quantityLabel);
    expect(t("pdp.vendor.heading")).toBe(messages.pdp.vendor.heading);
    expect(t("pdp.trust.returns")).toBe(messages.pdp.trust.returns);
    expect(t("pdp.trust.escrow")).toContain("Vergeo5");
    expect(formatK(123456, { locale: `${locale}-ZM` })).toMatch(/^K/);
  });
});

describe("Phase-1 bem/nya empty cart", () => {
  it.each([
    ["bem", bemCheckout],
    ["nya", nyaCheckout],
  ] as const)("%s empty cart copy renders vernacular", (locale, messages) => {
    const t = createTranslator({
      locale,
      messages: { checkout: messages },
      namespace: "checkout",
    });
    render(
      <EmptyState
        title={t("cart.emptyTitle")}
        body={t("cart.emptyBody")}
        data-testid="cart-empty-state"
      />,
    );
    expect(screen.getByTestId("cart-empty-state")).toHaveTextContent(messages.cart.emptyTitle);
    expect(screen.getByTestId("cart-empty-state")).toHaveTextContent(messages.cart.emptyBody);
    expect(screen.queryByText("Your cart is empty")).not.toBeInTheDocument();
  });
});

describe("Phase-1 bem/nya payment-disabled copy", () => {
  it.each([
    ["bem", bemCheckout],
    ["nya", nyaCheckout],
  ] as const)("%s paymentsDisabled is vernacular and distinct from EN", (locale, messages) => {
    const t = createTranslator({
      locale,
      messages: { checkout: messages },
      namespace: "checkout",
    });
    const text = t("checkout.payment.paymentsDisabled");
    expect(text).toBe(messages.checkout.payment.paymentsDisabled);
    expect(text).not.toBe(
      "Online payment is temporarily unavailable. Please use Cash on Delivery where available, or try again shortly.",
    );
    expect(text.toLowerCase()).toMatch(/cash|delivery|kod|lipil|payment|online/);
  });
});
