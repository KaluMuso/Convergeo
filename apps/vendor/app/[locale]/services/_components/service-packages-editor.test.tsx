import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  emptyDraft,
  priceOrderWarnings,
  validateDraft,
  type ServicePackage,
} from "../_lib/packages";

import { ServicePackagesEditor } from "./service-packages-editor";

const { list, upsert, archive } = vi.hoisted(() => ({
  list: vi.fn(),
  upsert: vi.fn(),
  archive: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "t", user: { id: "v" } }, loading: false }),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
vi.mock("../_lib/packages", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../_lib/packages")>();
  return { ...actual, createPackagesClient: () => ({ list, upsert, archive }) };
});

const BASIC: ServicePackage = {
  id: "p1",
  tier: "basic",
  name: "Logo only",
  description: null,
  price_ngwee: 75_000,
  delivery_days: 3,
  revisions: 1,
  includes: ["1 concept"],
  status: "active",
  updated_at: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("validateDraft", () => {
  it("converts kwacha to integer ngwee without float drift", () => {
    const verdict = validateDraft({ ...emptyDraft(), name: "Starter", price: "1,234.56" });
    expect(verdict.ok).toBe(true);
    if (verdict.ok) {
      expect(verdict.payload.price_ngwee).toBe(123_456);
      expect(Number.isInteger(verdict.payload.price_ngwee)).toBe(true);
    }
    const tricky = validateDraft({ ...emptyDraft(), name: "Starter", price: "0.29" });
    expect(tricky.ok && tricky.payload.price_ngwee).toBe(29);
  });

  it("sends null price for a request-a-quote package and null revisions when n/a", () => {
    const verdict = validateDraft({
      ...emptyDraft(),
      name: "Full brand",
      priceMode: "quote",
      price: "garbage",
      revisionsApplicable: false,
    });
    expect(verdict).toMatchObject({ ok: true, payload: { price_ngwee: null, revisions: null } });
  });

  it("flags each invalid field with an i18n key", () => {
    const verdict = validateDraft({
      ...emptyDraft(),
      name: "x",
      price: "12.345",
      deliveryDays: "0",
      revisions: "11",
      includes: Array.from({ length: 9 }, (_, i) => `item ${i}`).join("\n"),
    });
    expect(verdict.ok).toBe(false);
    if (!verdict.ok) {
      expect(verdict.errors).toEqual({
        name: "errors.name",
        price: "errors.price",
        delivery: "errors.delivery",
        revisions: "errors.revisions",
        includes: "errors.includes",
      });
    }
  });

  it("rejects fractional or text delivery days", () => {
    expect(
      validateDraft({ ...emptyDraft(), name: "ok", price: "10", deliveryDays: "2.5" }).ok,
    ).toBe(false);
    expect(
      validateDraft({ ...emptyDraft(), name: "ok", price: "10", deliveryDays: "two" }).ok,
    ).toBe(false);
  });
});

describe("priceOrderWarnings", () => {
  it("warns when a higher tier is cheaper, ignoring quote and archived tiers", () => {
    expect(
      priceOrderWarnings([
        { tier: "basic", price_ngwee: 50_000, status: "active" },
        { tier: "standard", price_ngwee: 40_000, status: "active" },
        { tier: "premium", price_ngwee: null, status: "active" },
      ]),
    ).toEqual([{ higher: "standard", lower: "basic" }]);
    expect(
      priceOrderWarnings([
        { tier: "basic", price_ngwee: 50_000, status: "archived" },
        { tier: "standard", price_ngwee: 40_000, status: "active" },
      ]),
    ).toEqual([]);
  });
});

describe("ServicePackagesEditor", () => {
  beforeEach(() => {
    list.mockResolvedValue({ service_id: "s1", items: [BASIC] });
    upsert.mockImplementation(
      async (_s: string, tier: string, payload: Record<string, unknown>) => ({
        ...BASIC,
        ...payload,
        id: `id-${tier}`,
        tier,
      }),
    );
    archive.mockResolvedValue({ ...BASIC, status: "archived" });
  });

  it("loads existing packages and offers the missing tiers", async () => {
    render(<ServicePackagesEditor serviceId="s1" />);
    expect(await screen.findByTestId("package-name-basic")).toHaveValue("Logo only");
    expect(screen.getByTestId("package-offer-standard")).toBeInTheDocument();
    expect(screen.getByTestId("package-offer-premium")).toBeInTheDocument();
  });

  it("saves a new tier with integer ngwee", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-offer-standard"));
    await user.type(screen.getByTestId("package-name-standard"), "Logo + cards");
    await user.type(screen.getByTestId("package-price-standard"), "1500.50");
    await user.click(screen.getByTestId("package-save-standard"));

    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1));
    const [serviceId, tier, payload] = upsert.mock.calls[0] ?? [];
    expect(serviceId).toBe("s1");
    expect(tier).toBe("standard");
    expect(payload).toMatchObject({ name: "Logo + cards", price_ngwee: 150_050, delivery_days: 3 });
    expect(await screen.findByTestId("package-message-standard")).toHaveTextContent("saved");
  });

  it("blocks an invalid save client-side", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-offer-premium"));
    await user.click(screen.getByTestId("package-save-premium"));
    expect(upsert).not.toHaveBeenCalled();
    expect(screen.getAllByText("errors.name").length).toBeGreaterThan(0);
  });

  it("archives through the API", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-archive-basic"));
    await waitFor(() => expect(archive).toHaveBeenCalledWith("s1", "basic"));
    expect(await screen.findByTestId("package-offer-basic")).toBeInTheDocument();
  });

  it("lets a vendor add a second and third package, each saved to its own tier", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    expect(await screen.findByTestId("packages-count")).toHaveTextContent("count");

    await user.click(await screen.findByTestId("package-offer-standard"));
    await user.type(screen.getByTestId("package-name-standard"), "Logo + cards");
    await user.type(screen.getByTestId("package-price-standard"), "150");
    await user.click(screen.getByTestId("package-save-standard"));
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(1));

    await user.click(screen.getByTestId("package-offer-premium"));
    await user.type(screen.getByTestId("package-name-premium"), "Full brand");
    await user.type(screen.getByTestId("package-price-premium"), "400");
    await user.click(screen.getByTestId("package-save-premium"));
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(2));

    expect(upsert.mock.calls.map((call) => call[1])).toEqual(["standard", "premium"]);
    // Editing the first package after adding others still works.
    await user.clear(screen.getByTestId("package-name-basic"));
    await user.type(screen.getByTestId("package-name-basic"), "Logo only v2");
    await user.click(screen.getByTestId("package-save-basic"));
    await waitFor(() => expect(upsert).toHaveBeenCalledTimes(3));
    expect(upsert.mock.calls[2]?.[1]).toBe("basic");
  });

  it("explains the three-package limit once every tier is offered", async () => {
    list.mockResolvedValue({
      service_id: "s1",
      items: (["basic", "standard", "premium"] as const).map((tier) => ({
        ...BASIC,
        id: `id-${tier}`,
        tier,
      })),
    });
    render(<ServicePackagesEditor serviceId="s1" />);
    expect(await screen.findByTestId("packages-limit-reached")).toBeInTheDocument();
    expect(screen.queryByTestId("package-offer-basic")).not.toBeInTheDocument();
  });

  it("does not show the limit message while a tier is still free", async () => {
    render(<ServicePackagesEditor serviceId="s1" />);
    await screen.findByTestId("packages-count");
    expect(screen.queryByTestId("packages-limit-reached")).not.toBeInTheDocument();
  });
});
