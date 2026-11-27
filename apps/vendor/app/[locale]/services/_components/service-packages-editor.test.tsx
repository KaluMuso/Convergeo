import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_PACKAGES, emptyDraft, validateDraft, type ServicePackage } from "../_lib/packages";

import { ServicePackagesEditor } from "./service-packages-editor";

const { list, create, update, remove, reorder } = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  reorder: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "t", user: { id: "v" } },
    loading: false,
  }),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => false }),
}));
vi.mock("../_lib/packages", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../_lib/packages")>();
  return {
    ...actual,
    createPackagesClient: () => ({ list, create, update, remove, reorder }),
  };
});

const BASIC: ServicePackage = {
  id: "p1",
  tier: null,
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
    const verdict = validateDraft({
      ...emptyDraft(),
      name: "Starter",
      price: "1,234.56",
    });
    expect(verdict.ok).toBe(true);
    if (verdict.ok) {
      expect(verdict.payload.price_ngwee).toBe(123_456);
      expect(Number.isInteger(verdict.payload.price_ngwee)).toBe(true);
    }
    const tricky = validateDraft({
      ...emptyDraft(),
      name: "Starter",
      price: "0.29",
    });
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
    expect(verdict).toMatchObject({
      ok: true,
      payload: { price_ngwee: null, revisions: null },
    });
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
      validateDraft({
        ...emptyDraft(),
        name: "ok",
        price: "10",
        deliveryDays: "2.5",
      }).ok,
    ).toBe(false);
    expect(
      validateDraft({
        ...emptyDraft(),
        name: "ok",
        price: "10",
        deliveryDays: "two",
      }).ok,
    ).toBe(false);
  });
});

const pkg = (n: number, over: Partial<ServicePackage> = {}): ServicePackage => ({
  ...BASIC,
  id: `p${n}`,
  name: `Package ${n}`,
  ...over,
});

describe("ServicePackagesEditor", () => {
  beforeEach(() => {
    list.mockResolvedValue({ service_id: "s1", items: [BASIC] });
    create.mockImplementation(async (_s: string, payload: Record<string, unknown>) => ({
      ...BASIC,
      ...payload,
      id: `new-id-${create.mock.calls.length}`,
    }));
    update.mockImplementation(async (_s: string, id: string, payload: Record<string, unknown>) => ({
      ...BASIC,
      ...payload,
      id,
    }));
    remove.mockResolvedValue(undefined);
    reorder.mockResolvedValue({ items: [] });
  });

  it("loads existing packages as editable cards", async () => {
    render(<ServicePackagesEditor serviceId="s1" />);
    expect(await screen.findByTestId("package-name-p1")).toHaveValue("Logo only");
    expect(screen.getByTestId("packages-count")).toHaveTextContent("count");
    expect(screen.getByTestId("package-add")).toBeEnabled();
  });

  it("adds a package with integer ngwee through create", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-add"));
    await user.type(screen.getByTestId("package-name-new-1"), "Logo + cards");
    await user.type(screen.getByTestId("package-price-new-1"), "1500.50");
    await user.click(screen.getByTestId("package-save-new-1"));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    const [serviceId, payload] = create.mock.calls[0] ?? [];
    expect(serviceId).toBe("s1");
    expect(payload).toMatchObject({
      name: "Logo + cards",
      price_ngwee: 150_050,
      delivery_days: 3,
    });
    expect(await screen.findByTestId("package-message-new-1")).toHaveTextContent("saved");
  });

  it("saving a second time updates the same package instead of creating another", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-add"));
    await user.type(screen.getByTestId("package-name-new-1"), "Extra");
    await user.type(screen.getByTestId("package-price-new-1"), "10");
    await user.click(screen.getByTestId("package-save-new-1"));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByTestId("package-save-new-1"));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("blocks an invalid save client-side", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-add"));
    await user.click(screen.getByTestId("package-save-new-1"));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getAllByText("errors.name").length).toBeGreaterThan(0);
  });

  it("edits an existing package through update", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.clear(await screen.findByTestId("package-name-p1"));
    await user.type(screen.getByTestId("package-name-p1"), "Logo only v2");
    await user.click(screen.getByTestId("package-save-p1"));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0]?.slice(0, 2)).toEqual(["s1", "p1"]);
    expect(update.mock.calls[0]?.[2]).toMatchObject({
      name: "Logo only v2",
      price_ngwee: 75_000,
    });
  });

  it("removes a saved package through the API and drops the card", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-archive-p1"));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("s1", "p1"));
    await waitFor(() => expect(screen.queryByTestId("package-panel-p1")).not.toBeInTheDocument());
  });

  it("discards an unsaved new package without calling the API", async () => {
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-add"));
    await user.click(screen.getByTestId("package-archive-new-1"));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByTestId("package-panel-new-1")).not.toBeInTheDocument();
  });

  it("reorders with the full active id list and updates the screen order", async () => {
    list.mockResolvedValue({
      service_id: "s1",
      items: [pkg(1), pkg(2), pkg(3)],
    });
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await screen.findByTestId("package-panel-p1");
    expect(screen.getByTestId("package-up-p1")).toBeDisabled();
    expect(screen.getByTestId("package-down-p3")).toBeDisabled();

    await user.click(screen.getByTestId("package-down-p1"));
    await waitFor(() => expect(reorder).toHaveBeenCalledWith("s1", ["p2", "p1", "p3"]));
    const order = screen
      .getAllByTestId(/^package-panel-/)
      .map((el) => el.getAttribute("data-testid"));
    expect(order).toEqual(["package-panel-p2", "package-panel-p1", "package-panel-p3"]);
  });

  it("puts the order back and says so when reordering fails", async () => {
    list.mockResolvedValue({ service_id: "s1", items: [pkg(1), pkg(2)] });
    reorder.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-down-p1"));
    expect(await screen.findByTestId("packages-list-message")).toHaveTextContent(
      "errors.reorderFailed",
    );
    const order = screen
      .getAllByTestId(/^package-panel-/)
      .map((el) => el.getAttribute("data-testid"));
    expect(order).toEqual(["package-panel-p1", "package-panel-p2"]);
  });

  it("shows the N of 10 counter and blocks adding an eleventh", async () => {
    list.mockResolvedValue({
      service_id: "s1",
      items: Array.from({ length: MAX_PACKAGES }, (_, i) => pkg(i + 1)),
    });
    render(<ServicePackagesEditor serviceId="s1" />);
    expect(await screen.findByTestId("packages-limit-reached")).toBeInTheDocument();
    expect(screen.getByTestId("packages-count")).toHaveTextContent("count");
    expect(screen.getByTestId("package-add")).toBeDisabled();
  });

  it("does not show the limit message below ten packages", async () => {
    list.mockResolvedValue({
      service_id: "s1",
      items: Array.from({ length: MAX_PACKAGES - 1 }, (_, i) => pkg(i + 1)),
    });
    render(<ServicePackagesEditor serviceId="s1" />);
    await screen.findByTestId("packages-count");
    expect(screen.queryByTestId("packages-limit-reached")).not.toBeInTheDocument();
    expect(screen.getByTestId("package-add")).toBeEnabled();
  });

  it("surfaces the server's cap error when a save loses a race", async () => {
    const { ApiError } = await import("@vergeo/config");
    create.mockRejectedValue(new ApiError("package_limit_reached", "x", { status: 409 }));
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-add"));
    await user.type(screen.getByTestId("package-name-new-1"), "One more");
    await user.type(screen.getByTestId("package-price-new-1"), "10");
    await user.click(screen.getByTestId("package-save-new-1"));
    expect(await screen.findByTestId("package-message-new-1")).toHaveTextContent(
      "errors.limitReached",
    );
  });

  it("lists a legacy removed package with an offer-again button that respects the cap", async () => {
    list.mockResolvedValue({
      service_id: "s1",
      items: [pkg(1), pkg(2, { status: "archived", tier: "premium" })],
    });
    const user = userEvent.setup();
    render(<ServicePackagesEditor serviceId="s1" />);
    await user.click(await screen.findByTestId("package-offer-p2"));
    expect(await screen.findByTestId("package-name-p2")).toHaveValue("Package 2");
  });
});
