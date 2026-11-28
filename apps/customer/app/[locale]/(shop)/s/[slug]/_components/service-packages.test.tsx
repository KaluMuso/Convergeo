// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { formatK } from "@vergeo/i18n";
import { createTranslator } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../../packages/i18n/messages/en/catalog.json";
import servicesMessages from "../../../../../../../../packages/i18n/messages/en/services.json";
import { useSession } from "../../../../../../lib/customer-session";

import { ServicePackages } from "./service-packages";
import { buildPrefill, normalisePackages, type ServicePackage } from "./service-packages-model";

import type { RequestQuoteLabels } from "../../../_components/pdp/request-quote-button";

vi.mock("../../../../../../lib/customer-session", () => ({
  useSession: vi.fn(),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/en/s/svc-1" }));

const createRfq = vi.fn();
vi.mock("../../../../../../lib/rfq-api", () => ({
  createRfqApiClient: () => ({
    createRfq: (...args: unknown[]) => createRfq(...args),
  }),
  RFQ_DETAILS_MAX_CHARS: 4000,
}));

const translator = createTranslator({
  locale: "en",
  messages: { services: servicesMessages },
  namespace: "services.packages",
});
const t = (key: string, values?: Record<string, string | number>) =>
  (translator as unknown as (k: string, v?: Record<string, string | number>) => string)(
    key,
    values,
  );
const quoteLabels = catalogMessages.pdp.requestQuote as RequestQuoteLabels;

const BASIC: ServicePackage = {
  id: "pkg-basic",
  name: "Logo only",
  description: "One concept",
  price_ngwee: 75_000,
  delivery_days: 3,
  revisions: 1,
  includes: ["1 concept", "PNG + PDF"],
};
const PREMIUM: ServicePackage = {
  id: "pkg-premium",
  name: "Full brand",
  description: null,
  price_ngwee: null,
  delivery_days: 14,
  revisions: null,
  includes: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("normalisePackages", () => {
  it("keeps the vendor's order, drops duplicates and junk, and never keeps non-integer money", () => {
    const out = normalisePackages([
      PREMIUM,
      { ...BASIC, price_ngwee: 750.5 },
      { ...BASIC, name: "duplicate id" },
      { id: "x", tier: "deluxe", name: "Odd label" },
      null,
      "junk",
    ]);
    expect(out.map((p) => p.id)).toEqual(["pkg-premium", "pkg-basic", "x"]);
    expect(out[1]?.price_ngwee).toBeNull(); // 750.5 is not integer ngwee
    expect(out[2]?.tier).toBeNull(); // unknown legacy label is dropped, package kept
  });

  it("accepts the legacy tier label but does not order by it", () => {
    const out = normalisePackages([
      { ...PREMIUM, tier: "premium" },
      { ...BASIC, tier: "basic" },
    ]);
    expect(out.map((p) => p.tier)).toEqual(["premium", "basic"]);
  });

  it("shows up to ten packages and no more", () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      ...BASIC,
      id: `p${i}`,
      name: `P${i}`,
    }));
    const out = normalisePackages(many);
    expect(out).toHaveLength(10);
    expect(out[0]?.id).toBe("p0");
    expect(out[9]?.id).toBe("p9");
  });

  it("returns [] for anything that is not a list", () => {
    expect(normalisePackages(undefined)).toEqual([]);
    expect(normalisePackages({})).toEqual([]);
  });
});

describe("buildPrefill", () => {
  it("names the package, formatted price and delivery", () => {
    const text = buildPrefill(BASIC, t, formatK);
    expect(text).toContain("Logo only");
    expect(text).toContain(formatK(75_000));
    expect(text).toContain("3 days");
  });

  it("says 'to be quoted' for a request-a-quote package", () => {
    expect(buildPrefill(PREMIUM, t, formatK)).toContain("to be quoted");
  });
});

describe("ServicePackages", () => {
  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      session: { access_token: "token" },
      loading: false,
    } as ReturnType<typeof useSession>);
    createRfq.mockResolvedValue({
      thread: { id: "thread-1" },
      message: { id: "m-1" },
      reused_existing_thread: false,
    });
  });

  it("renders nothing without packages", () => {
    const { container } = render(
      <ServicePackages
        locale="en"
        serviceId="svc-1"
        vendorName="Shop"
        packages={[]}
        t={t}
        quoteLabels={quoteLabels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("compares packages with price, delivery and revisions", () => {
    render(
      <ServicePackages
        locale="en"
        serviceId="svc-1"
        vendorName="Shop"
        packages={[BASIC, PREMIUM]}
        t={t}
        quoteLabels={quoteLabels}
      />,
    );
    const basic = screen.getByTestId("service-package-pkg-basic");
    expect(within(basic).getByTestId("service-package-price")).toHaveTextContent(formatK(75_000));
    expect(basic).toHaveTextContent("Delivered in 3 days");
    expect(basic).toHaveTextContent("1 revision");
    const premium = screen.getByTestId("service-package-pkg-premium");
    expect(premium).toHaveTextContent("Price on request");
    expect(premium).toHaveTextContent("Revisions not applicable");
    expect(screen.getByText(servicesMessages.packages.noPaymentNote)).toBeInTheDocument();
  });

  it("renders ten packages in the vendor's order", () => {
    const ten = Array.from({ length: 10 }, (_, i) => ({
      ...BASIC,
      id: `p${i}`,
      name: `Pack ${i}`,
    }));
    render(
      <ServicePackages
        locale="en"
        serviceId="svc-1"
        vendorName="Shop"
        packages={ten}
        t={t}
        quoteLabels={quoteLabels}
      />,
    );
    const cards = screen.getAllByTestId(/^service-package-p\d$/);
    expect(cards.map((c) => within(c).getByRole("heading", { level: 3 }).textContent)).toEqual(
      ten.map((p) => p.name),
    );
  });

  it("opens the quote request prefilled and sends the package id", async () => {
    const user = userEvent.setup();
    render(
      <ServicePackages
        locale="en"
        serviceId="svc-1"
        vendorName="Shop"
        packages={[BASIC, PREMIUM]}
        t={t}
        quoteLabels={quoteLabels}
      />,
    );
    await user.click(screen.getByTestId("service-package-cta-pkg-basic"));
    const textarea = await screen.findByTestId("pdp-request-quote-details");
    expect((textarea as HTMLTextAreaElement).value).toContain("Logo only");

    await user.type(textarea, "For my bakery");
    await user.click(screen.getByTestId("pdp-request-quote-submit"));

    await waitFor(() => expect(createRfq).toHaveBeenCalledTimes(1));
    const payload = createRfq.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.service_id).toBe("svc-1");
    expect(payload.package_id).toBe("pkg-basic");
    expect(String(payload.requested_details)).toContain("For my bakery");
  });
});
