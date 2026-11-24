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

vi.mock("../../../../../../lib/customer-session", () => ({ useSession: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/en/s/svc-1" }));

const createRfq = vi.fn();
vi.mock("../../../../../../lib/rfq-api", () => ({
  createRfqApiClient: () => ({ createRfq: (...args: unknown[]) => createRfq(...args) }),
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
  tier: "basic",
  name: "Logo only",
  description: "One concept",
  price_ngwee: 75_000,
  delivery_days: 3,
  revisions: 1,
  includes: ["1 concept", "PNG + PDF"],
};
const PREMIUM: ServicePackage = {
  id: "pkg-premium",
  tier: "premium",
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
  it("orders by tier, drops duplicates and junk, and never keeps non-integer money", () => {
    const out = normalisePackages([
      PREMIUM,
      { ...BASIC, price_ngwee: 750.5 },
      { ...BASIC, id: "dup" },
      { id: "x", tier: "deluxe" },
      null,
      "nope",
    ]);
    expect(out.map((p) => p.tier)).toEqual(["basic", "premium"]);
    expect(out[0]?.price_ngwee).toBeNull();
    expect(out[0]?.id).toBe("pkg-basic");
  });

  it("returns [] for anything that is not a list", () => {
    expect(normalisePackages(undefined)).toEqual([]);
    expect(normalisePackages({})).toEqual([]);
  });
});

describe("buildPrefill", () => {
  it("names the tier, package, formatted price and delivery", () => {
    const text = buildPrefill(BASIC, t, formatK);
    expect(text).toContain("Basic");
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

  it("compares tiers with price, delivery and revisions", () => {
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
    const basic = screen.getByTestId("service-package-basic");
    expect(within(basic).getByTestId("service-package-price")).toHaveTextContent(formatK(75_000));
    expect(basic).toHaveTextContent("Delivered in 3 days");
    expect(basic).toHaveTextContent("1 revision");
    const premium = screen.getByTestId("service-package-premium");
    expect(premium).toHaveTextContent("Price on request");
    expect(premium).toHaveTextContent("Revisions not applicable");
    expect(screen.getByText(servicesMessages.packages.noPaymentNote)).toBeInTheDocument();
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
    await user.click(screen.getByTestId("service-package-cta-basic"));
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
