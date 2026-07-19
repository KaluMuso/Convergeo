// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";
import frCatalog from "../../../../../../packages/i18n/messages/fr/catalog.json";
import zhCatalog from "../../../../../../packages/i18n/messages/zh/catalog.json";

import { HomeTrustStrip } from "./home-trust-strip";

afterEach(() => {
  cleanup();
});

function labelsFrom(messages: typeof catalogMessages) {
  const t = createTranslator({
    locale: "en",
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

const ACTIVE_PAYMENT_CLAIMS =
  /pay with mobile money|mobile-money payouts|card checkout is live|momo checkout is live|start selling today/i;

describe("HomeTrustStrip (CUST-HOME-01)", () => {
  it("renders localised trust items", () => {
    render(<HomeTrustStrip labels={labelsFrom(catalogMessages)} />);
    expect(screen.getByTestId("home-trust-strip")).toBeInTheDocument();
    expect(screen.getByTestId("home-trust-sellers")).toHaveTextContent(
      catalogMessages.home.trust.sellers,
    );
    expect(screen.getByTestId("home-trust-fulfillment")).toHaveTextContent(
      catalogMessages.home.trust.fulfillment,
    );
    expect(screen.getByTestId("home-trust-returns")).toHaveTextContent(
      catalogMessages.home.trust.returns,
    );
    expect(screen.getByTestId("home-trust-escrow")).toHaveTextContent(
      catalogMessages.home.trust.escrow,
    );
  });

  it("keeps en/fr/zh trust + sell copy free of false active-payment language", () => {
    for (const messages of [catalogMessages, frCatalog, zhCatalog]) {
      const blob = [
        messages.home.trust.escrow,
        messages.home.trust.fulfillment,
        messages.home.hero.escrowLine,
        messages.home.hero.fallbackSubtitle,
        messages.home.sellCta.body,
        messages.home.sellCta.cta,
      ].join(" ");
      expect(blob).not.toMatch(ACTIVE_PAYMENT_CLAIMS);
    }
  });
});
