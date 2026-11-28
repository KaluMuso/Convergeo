// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import bemCatalog from "../../../../../../packages/i18n/messages/bem/catalog.json";
import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";
import frCatalog from "../../../../../../packages/i18n/messages/fr/catalog.json";
import nyaCatalog from "../../../../../../packages/i18n/messages/nya/catalog.json";
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
    ariaLabel: t("home.trustStrip.ariaLabel"),
    cod: t("home.trustStrip.cod"),
    verified: t("home.trustStrip.verified"),
    lusaka: t("home.trustStrip.lusaka"),
    returns: t("home.trustStrip.returns"),
  };
}

/** Payments are live: the strip may mention Mobile Money, never the "MoMo" shorthand. */
const BANNED_SHORTHAND = /\bmomo\b/i;

describe("HomeTrustStrip", () => {
  it("renders the four trust items in order", () => {
    render(<HomeTrustStrip labels={labelsFrom(catalogMessages)} />);
    const strip = screen.getByTestId("home-trust-strip");
    expect(strip).toHaveAttribute("aria-label", "Why shop on Vergeo5");
    const items = within(strip).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      catalogMessages.home.trustStrip.cod,
      "Verified sellers",
      "Lusaka delivery",
      "Easy returns",
    ]);
  });

  it("keeps decorative glyphs out of the accessibility tree", () => {
    const { container } = render(<HomeTrustStrip labels={labelsFrom(catalogMessages)} />);
    for (const svg of container.querySelectorAll("svg")) {
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("ships en/fr/zh strings and flags bem/nya as untranslated placeholders", () => {
    for (const messages of [catalogMessages, frCatalog, zhCatalog]) {
      const strip = messages.home.trustStrip;
      expect(Object.values(strip).every((value) => value.length > 0)).toBe(true);
      expect(Object.values(strip).join(" ")).not.toMatch(BANNED_SHORTHAND);
      expect(strip.cod).not.toMatch(/^⚠/);
    }
    expect(frCatalog.home.trustStrip.cod).not.toBe(catalogMessages.home.trustStrip.cod);
    expect(zhCatalog.home.trustStrip.cod).not.toBe(catalogMessages.home.trustStrip.cod);
    for (const messages of [bemCatalog, nyaCatalog]) {
      expect(messages.home.trustStrip.cod).toBe(`⚠ ${catalogMessages.home.trustStrip.cod}`);
    }
  });

  it("keeps en/fr/zh trust + sell copy free of claims that are not live yet (payouts)", () => {
    const claims = /mobile-money payouts|start selling today/i;
    for (const messages of [catalogMessages, frCatalog, zhCatalog]) {
      const blob = [
        messages.home.hero.escrowLine,
        messages.home.hero.fallbackSubtitle,
        messages.home.sellCta.body,
        messages.home.sellCta.cta,
      ].join(" ");
      expect(blob).not.toMatch(claims);
    }
  });
});
