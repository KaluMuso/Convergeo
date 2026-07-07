// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer, type FooterColumn } from "./footer";

const LEGAL_KEYS_USED_BY_PAGES = [
  "updated",
  "onThisPage",
  "counselNote",
  "terms.title",
  "terms.description",
  "terms.sections.introduction.heading",
  "terms.sections.introduction.body",
  "terms.sections.marketplace.heading",
  "terms.sections.marketplace.body",
  "terms.sections.escrow.heading",
  "terms.sections.escrow.body",
  "terms.sections.pricing.heading",
  "terms.sections.pricing.body",
  "terms.sections.orders.heading",
  "terms.sections.orders.body",
  "terms.sections.tax.heading",
  "terms.sections.tax.body",
  "terms.sections.prohibited.heading",
  "terms.sections.prohibited.body",
  "terms.sections.liability.heading",
  "terms.sections.liability.body",
  "terms.sections.changes.heading",
  "terms.sections.changes.body",
  "terms.sections.contact.heading",
  "terms.sections.contact.body",
  "privacy.title",
  "privacy.description",
  "privacy.sections.introduction.heading",
  "privacy.sections.introduction.body",
  "privacy.sections.controller.heading",
  "privacy.sections.controller.body",
  "privacy.sections.dataCollected.heading",
  "privacy.sections.dataCollected.body",
  "privacy.sections.legalBasis.heading",
  "privacy.sections.legalBasis.body",
  "privacy.sections.use.heading",
  "privacy.sections.use.body",
  "privacy.sections.sharing.heading",
  "privacy.sections.sharing.body",
  "privacy.sections.retention.heading",
  "privacy.sections.retention.body",
  "privacy.sections.security.heading",
  "privacy.sections.security.body",
  "privacy.sections.dataRights.heading",
  "privacy.sections.dataRights.body",
  "privacy.sections.cookies.heading",
  "privacy.sections.cookies.body",
  "privacy.sections.children.heading",
  "privacy.sections.children.body",
  "privacy.sections.changes.heading",
  "privacy.sections.changes.body",
  "privacy.sections.contact.heading",
  "privacy.sections.contact.body",
  "returns.title",
  "returns.description",
  "returns.sections.introduction.heading",
  "returns.sections.introduction.body",
  "returns.sections.lane1.heading",
  "returns.sections.lane1.body",
  "returns.sections.lane1Steps.heading",
  "returns.sections.lane1Steps.body",
  "returns.sections.lane2.heading",
  "returns.sections.lane2.body",
  "returns.sections.lane2Refund.heading",
  "returns.sections.lane2Refund.body",
  "returns.sections.lane2Steps.heading",
  "returns.sections.lane2Steps.body",
  "returns.sections.escrow.heading",
  "returns.sections.escrow.body",
  "returns.sections.exclusions.heading",
  "returns.sections.exclusions.body",
  "returns.sections.contact.heading",
  "returns.sections.contact.body",
  "vendorAgreement.title",
  "vendorAgreement.description",
  "vendorAgreement.sections.introduction.heading",
  "vendorAgreement.sections.introduction.body",
  "vendorAgreement.sections.commissions.heading",
  "vendorAgreement.sections.commissions.body",
  "vendorAgreement.sections.payouts.heading",
  "vendorAgreement.sections.payouts.body",
  "vendorAgreement.sections.listing.heading",
  "vendorAgreement.sections.listing.body",
  "vendorAgreement.sections.returns.heading",
  "vendorAgreement.sections.returns.body",
  "vendorAgreement.sections.prohibited.heading",
  "vendorAgreement.sections.prohibited.body",
  "vendorAgreement.sections.kyc.heading",
  "vendorAgreement.sections.kyc.body",
  "vendorAgreement.sections.termination.heading",
  "vendorAgreement.sections.termination.body",
  "vendorAgreement.sections.changes.heading",
  "vendorAgreement.sections.changes.body",
  "vendorAgreement.sections.contact.heading",
  "vendorAgreement.sections.contact.body",
  "vendorAgreement.commissions.categoryHeader",
  "vendorAgreement.commissions.rateHeader",
  "vendorAgreement.commissions.electronics",
  "vendorAgreement.commissions.electronicsRate",
  "vendorAgreement.commissions.homeGoods",
  "vendorAgreement.commissions.homeGoodsRate",
  "vendorAgreement.commissions.fashionBeauty",
  "vendorAgreement.commissions.fashionBeautyRate",
  "vendorAgreement.commissions.services",
  "vendorAgreement.commissions.servicesRate",
  "vendorAgreement.commissions.eventTickets",
  "vendorAgreement.commissions.eventTicketsRate",
  "vendorAgreement.commissions.suppliesWholesale",
  "vendorAgreement.commissions.suppliesWholesaleRate",
  "vendorAgreement.commissions.groceriesStaples",
  "vendorAgreement.commissions.groceriesStaplesRate",
  "vendorAgreement.commissions.defaultCategory",
  "vendorAgreement.commissions.defaultRate",
  "vendorAgreement.commissions.freeEvents",
  "vendorAgreement.commissions.freeEventsRate",
  "vendorAgreement.commissions.footnote",
] as const;

function getNestedValue(messages: Record<string, unknown>, key: string): unknown {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null || !(part in node)) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

function hasFlatDottedKeys(messages: Record<string, unknown>): string[] {
  return Object.keys(messages).filter((key) => key.includes("."));
}

const columns: FooterColumn[] = [
  {
    key: "legal",
    heading: "Legal",
    links: [
      { key: "terms", href: "/en/legal/terms", label: "Terms" },
      { key: "privacy", href: "/en/legal/privacy", label: "Privacy" },
    ],
  },
  {
    key: "help",
    heading: "Help",
    links: [{ key: "help", href: "/en/help", label: "Help centre" }],
  },
];

describe("Footer", () => {
  it("renders provided links and labels via LinkComponent", () => {
    function TestLink({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
      className?: string;
      style?: React.CSSProperties;
    }) {
      return (
        <a href={href} data-testid={`link-${href}`} {...rest}>
          {children}
        </a>
      );
    }

    render(
      <Footer
        appName="App"
        copyright="© 2026 App"
        columns={columns}
        paymentNote="MoMo"
        LinkComponent={TestLink}
      />,
    );

    expect(screen.getByText("Terms")).toBeInTheDocument();
    expect(screen.getByText("Privacy")).toBeInTheDocument();
    expect(screen.getByText("Help centre")).toBeInTheDocument();
    expect(screen.getByText("MoMo")).toBeInTheDocument();
    expect(screen.getByTestId("link-/en/legal/terms")).toHaveAttribute("href", "/en/legal/terms");
  });

  it("does not embed hardcoded user-facing link labels", () => {
    const { container } = render(
      <Footer appName="Brand" copyright="Copy" columns={columns} paymentNote="Pay" />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Terms of service|Privacy policy|Vergeo5/);
    expect(text).toContain("Terms");
    expect(text).toContain("Brand");
  });
});

describe("legal i18n completeness", () => {
  const legalPath = join(
    dirname(fileURLToPath(import.meta.url)),
    "../../../packages/i18n/messages/en/legal.json",
  );
  const legal = JSON.parse(readFileSync(legalPath, "utf8")) as Record<string, unknown>;

  it("is valid nested JSON with no flat dotted keys", () => {
    expect(hasFlatDottedKeys(legal)).toEqual([]);
    expect(legal.terms).toBeTypeOf("object");
    expect(legal.privacy).toBeTypeOf("object");
    expect(legal.returns).toBeTypeOf("object");
    expect(legal.vendorAgreement).toBeTypeOf("object");
  });

  it("contains every key referenced by the four legal pages", () => {
    const missing = LEGAL_KEYS_USED_BY_PAGES.filter((key) => {
      const value = getNestedValue(legal, key);
      return typeof value !== "string" || value.length === 0;
    });
    expect(missing).toEqual([]);
  });
});
