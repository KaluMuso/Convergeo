// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import bemCatalog from "../../../../../../packages/i18n/messages/bem/catalog.json";
import bemCommon from "../../../../../../packages/i18n/messages/bem/common.json";
import enCatalog from "../../../../../../packages/i18n/messages/en/catalog.json";
import enCommon from "../../../../../../packages/i18n/messages/en/common.json";
import enNav from "../../../../../../packages/i18n/messages/en/nav.json";
import frCatalog from "../../../../../../packages/i18n/messages/fr/catalog.json";
import frCommon from "../../../../../../packages/i18n/messages/fr/common.json";
import nyaCatalog from "../../../../../../packages/i18n/messages/nya/catalog.json";
import nyaCommon from "../../../../../../packages/i18n/messages/nya/common.json";
import zhCatalog from "../../../../../../packages/i18n/messages/zh/catalog.json";
import zhCommon from "../../../../../../packages/i18n/messages/zh/common.json";

import { ServiceInfoBar } from "./service-info-bar";

afterEach(cleanup);

describe("ServiceInfoBar", () => {
  it("renders factual fulfillment messaging", () => {
    render(
      <ServiceInfoBar
        labels={{
          ariaLabel: enCatalog.home.serviceBar.ariaLabel,
          message: enCatalog.home.serviceBar.message,
        }}
      />,
    );
    const bar = screen.getByTestId("service-info-bar");
    expect(bar).toHaveTextContent(/Lusaka delivery/i);
    expect(bar).toHaveTextContent(/cash on delivery/i);
    expect(bar).not.toHaveTextContent(/MoMo checkout is live/i);
  });
});

describe("site-wide payment trust copy (live online payments)", () => {
  const locales = {
    en: { catalog: enCatalog, common: enCommon },
    bem: { catalog: bemCatalog, common: bemCommon },
    nya: { catalog: nyaCatalog, common: nyaCommon },
    fr: { catalog: frCatalog, common: frCommon },
    zh: { catalog: zhCatalog, common: zhCommon },
  };

  it.each(Object.entries(locales))(
    "%s header strip and footer keep placeholders out",
    (_locale, messages) => {
      const strings = [
        messages.catalog.home.serviceBar.message,
        messages.common.paymentTrust.footerSeal,
        messages.common.paymentTrust.footerPaymentNote,
      ];
      for (const value of strings) {
        expect(value.trim()).not.toBe("");
        expect(value).not.toMatch(/[{}]/);
      }
    },
  );

  it("English footer mentions escrow or mobile money", () => {
    expect(enCommon.paymentTrust.footerPaymentNote).toMatch(
      /mobile money|escrow|MoMo/i,
    );
    expect(enCommon.paymentTrust.footerSeal).toMatch(/Held by Convergeo/i);
  });
});
