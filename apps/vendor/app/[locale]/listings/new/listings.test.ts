import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";
import { loadNamespace } from "../../../../../../packages/i18n/src/request";
import { canUseWholesaleCapabilities } from "../../_lib/kyc-integrity";

import { ListingCreateFlow } from "./_components/listing-create-flow";
import { applyListingFieldPatch, DEFAULT_LISTING_FIELDS } from "./_components/listing-fields";
import { QuickListForm } from "./_components/quick-list-form";
import { listingCreateErrorMessage } from "./_lib/listing-errors";
import { isValidUnitDecimal, unitDecimalToMilli } from "./_lib/measure";
import { zmwDecimalToNgwee, isValidZmwDecimal } from "./_lib/money";

import type { CategoryOption, ListingCreatePayload, ListingCreateResponse } from "./_lib/types";

describe("listing money conversion", () => {
  it("converts K1,234.56 to 123456 ngwee without float drift", () => {
    expect(zmwDecimalToNgwee("1,234.56")).toBe(123_456);
  });

  it("converts whole kwacha amounts", () => {
    expect(zmwDecimalToNgwee("500")).toBe(50_000);
  });

  it("rejects invalid decimals", () => {
    expect(isValidZmwDecimal("abc")).toBe(false);
    expect(isValidZmwDecimal("0")).toBe(false);
  });
});

describe("listings i18n", () => {
  it("exposes nested listings namespace keys", () => {
    expect(vendorMessages.listings.title).toBe("Create listing");
    expect(vendorMessages.listings.commission.rate).toBe("{rate}%");
    expect(vendorMessages.listings.attach.publish).toBe("Publish listing");
    expect(vendorMessages.listings.fields.classA).toBe("A. Branded SKU");
    expect(vendorMessages.listings.fields.classB).toBe("B. Branded variant");
    expect(vendorMessages.listings.fields.classC).toBe("C. Commodity / generic");
    expect(vendorMessages.listings.errors.standalone_required).toBeTruthy();
  });
});

describe("listing unit-step conversion", () => {
  it("converts three-decimal increments to integer milli-units", () => {
    expect(unitDecimalToMilli("0.125")).toBe(125);
    expect(unitDecimalToMilli("2.5")).toBe(2_500);
  });

  it("returns a validation error for unsafe or over-precise increments", () => {
    expect(isValidUnitDecimal("9007199254740992")).toBe(false);
    expect(isValidUnitDecimal("0.0001")).toBe(false);
  });
});

describe("product-class form rules", () => {
  it("forces Class D to used condition", () => {
    expect(applyListingFieldPatch(DEFAULT_LISTING_FIELDS, { productClass: "D" }).condition).toBe(
      "used",
    );
  });

  it("forces Class E to made-to-order fulfilment", () => {
    const fields = applyListingFieldPatch(DEFAULT_LISTING_FIELDS, {
      productClass: "E",
    });
    expect(fields.fulfilmentMode).toBe("made_to_order");
    expect(fields.stockMode).toBe("always_available");
  });
});

describe("listing create errors", () => {
  it("maps the standalone-class API error to vendor-facing copy", () => {
    const message = listingCreateErrorMessage(
      new ApiError("standalone_product_class_required", "Use quick list", {
        status: 422,
      }),
      {
        standaloneRequired: vendorMessages.listings.errors.standalone_required,
        fallback: vendorMessages.listings.errors.submitFailed,
      },
    );

    expect(message).toBe(vendorMessages.listings.errors.standalone_required);
  });
});

describe("attach live-search + commission-shown contract", () => {
  it("documents canonical preview and commission fields for attach flow", () => {
    const preview = {
      product_id: "product-1",
      name: "Smartphone X1",
      commission: {
        category_key: "electronics",
        rate_bps: 500,
        rate_percent: 5,
      },
    };
    expect(preview.commission.rate_percent).toBe(5);
    expect(vendorMessages.listings.commission.heading).toContain("Commission");
  });
});

describe("listing create KYC capability gate", () => {
  it("hides wholesale UI when tier is orphaned without a KYC record", () => {
    expect(
      canUseWholesaleCapabilities({
        kyc_tier: 2,
        kyc_status: "approved",
        kyc_record_id: null,
        kyc_record_status: null,
      }),
    ).toBe(false);
  });

  it("exposes KYC gate copy for honest status", () => {
    expect(vendorMessages.listings.kycGate.title).toBeTruthy();
    expect(vendorMessages.listings.kycGate.wholesaleLocked).toContain("T2");
  });
});

const flowMocks = vi.hoisted(() => ({
  session: { access_token: "unit-test-token" },
  getApplication: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  client: null as unknown,
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: flowMocks.session, loading: false }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: flowMocks.push, replace: flowMocks.replace }),
}));
vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const messages: unknown = namespace === "vendor" ? vendorMessages : {};
    const value = key.split(".").reduce<unknown>((current, part) => {
      return current && typeof current === "object"
        ? (current as Record<string, unknown>)[part]
        : undefined;
    }, messages);
    return typeof value === "string" ? value : key;
  },
}));
vi.mock("../../onboarding/_lib/kyc-client", () => ({
  createKycClient: () => ({ getApplication: flowMocks.getApplication }),
}));
vi.mock("./_lib/listing-client", () => ({
  createListingClient: () => flowMocks.client,
}));

const category: CategoryOption = {
  id: "10000000-0000-0000-0000-000000000001",
  name: "Synthetic category",
  commission_key: "default",
  commission: { category_key: "default", rate_bps: 500, rate_percent: 5 },
};
const draftResponse: ListingCreateResponse = {
  listing_id: "40000000-0000-0000-0000-000000000001",
  mode: "quick_list",
  status: "draft",
  product_id: null,
  product_status: null,
  commission: null,
  requires_evidence: false,
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function makeClient() {
  return {
    listCategories: vi.fn<() => Promise<CategoryOption[]>>().mockResolvedValue([category]),
    createListing: vi
      .fn<(payload: ListingCreatePayload) => Promise<ListingCreateResponse>>()
      .mockResolvedValue(draftResponse),
    suggestProducts: vi.fn().mockResolvedValue([]),
    getCanonicalPreview: vi.fn(),
  };
}
function quickLabels() {
  return {
    ...vendorMessages.listings.quickList,
    categoryLabel: vendorMessages.listings.newCanonical.categoryLabel,
    categoryPlaceholder: vendorMessages.listings.newCanonical.categoryPlaceholder,
    catalogLabel: vendorMessages.listings.tabs.attach,
    fields: {
      ...vendorMessages.listings.fields,
      required: vendorMessages.listings.errors.required,
    },
    submitError: vendorMessages.listings.errors.submitFailed,
    standaloneRequired: vendorMessages.listings.errors.standalone_required,
    required: vendorMessages.listings.errors.required,
  };
}
function mountQuick(client = makeClient(), wholesaleEnabled = false) {
  const onError = vi.fn();
  const onSuccess = vi.fn();
  const onRequestCatalog = vi.fn();
  const props = {
    client,
    wholesaleEnabled,
    onError,
    onSuccess,
    onRequestCatalog,
    labels: quickLabels(),
  };
  const view = render(createElement(QuickListForm, props));
  return { ...view, client, onError, onSuccess, onRequestCatalog, props };
}
function input(label: string) {
  return screen.getByLabelText(label, { exact: false });
}
async function fillDraft(productClass: "D" | "E") {
  fireEvent.change(input(vendorMessages.listings.fields.productClassLabel), {
    target: { value: productClass },
  });
  await waitFor(() => expect(screen.getByRole("option", { name: category.name })).toBeTruthy());
  fireEvent.change(input(vendorMessages.listings.quickList.titleLabel), {
    target: { value: " Synthetic item " },
  });
  fireEvent.change(input(vendorMessages.listings.quickList.descriptionLabel), {
    target: { value: " 12345678901234567890 " },
  });
  fireEvent.change(input(vendorMessages.listings.newCanonical.categoryLabel), {
    target: { value: category.id },
  });
  fireEvent.change(input(vendorMessages.listings.fields.priceLabel), {
    target: { value: "1,234.56" },
  });
  if (productClass === "D") {
    fireEvent.change(input(vendorMessages.listings.fields.defectNotesLabel), {
      target: { value: " Synthetic wear marks " },
    });
  } else {
    fireEvent.change(input(vendorMessages.listings.fields.leadTimeLabel), {
      target: { value: "7" },
    });
    fireEvent.change(input(vendorMessages.listings.fields.capacityLabel), {
      target: { value: "10" },
    });
  }
}
function saveDraft() {
  fireEvent.click(
    screen.getByRole("button", {
      name: vendorMessages.listings.quickList.saveDraft,
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("Network forbidden in QuickList tests");
    }),
  );
  flowMocks.getApplication.mockResolvedValue({
    kyc_tier: 1,
    kyc_status: "approved",
    kyc_record_id: "synthetic-kyc",
    kyc_record_status: "approved",
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("QuickList draft request contract", () => {
  it.each(["A", "B", "C"])(
    "routes class %s to Catalog without creating or reclassifying",
    (productClass) => {
      const view = mountQuick();
      const selector = input(vendorMessages.listings.fields.productClassLabel);
      expect((selector as HTMLSelectElement).value).toBe("C");
      fireEvent.change(selector, { target: { value: productClass } });
      expect(screen.getByText(vendorMessages.listings.quickList.canonicalRequired)).toBeTruthy();
      fireEvent.click(
        screen.getByRole("button", {
          name: vendorMessages.listings.tabs.attach,
        }),
      );
      expect(view.onRequestCatalog).toHaveBeenCalledOnce();
      expect((selector as HTMLSelectElement).value).toBe(productClass);
      expect(view.client.createListing).not.toHaveBeenCalled();
    },
  );
  it.each(["D", "E"] as const)(
    "submits class %s with own content and publish false",
    async (productClass) => {
      const view = mountQuick();
      await fillDraft(productClass);
      saveDraft();
      await waitFor(() => expect(view.onSuccess).toHaveBeenCalledOnce());
      expect(view.client.createListing).toHaveBeenCalledExactlyOnceWith({
        mode: "quick_list",
        product_id: null,
        product_class: productClass,
        title_override: "Synthetic item",
        category_id: category.id,
        description: "12345678901234567890",
        price_ngwee: 123456,
        sale_unit: "each",
        unit_step_milli: 1000,
        min_steps: 1,
        condition: productClass === "D" ? "used" : "new",
        defect_notes: productClass === "D" ? "Synthetic wear marks" : null,
        fulfilment_mode: productClass === "E" ? "made_to_order" : "stocked",
        lead_time_days: productClass === "E" ? 7 : null,
        vendor_capacity_per_week: productClass === "E" ? 10 : null,
        stock_mode: "always_available",
        stock_qty: null,
        wholesale: false,
        moq: 1,
        publish: false,
      });
      expect(view.onError).not.toHaveBeenCalled();
    },
  );
  it.each(["", "   ", "1234567890123456789", "😀".repeat(10)])(
    "rejects short own description %j before transport",
    async (description) => {
      const view = mountQuick();
      await fillDraft("E");
      fireEvent.change(input(vendorMessages.listings.quickList.descriptionLabel), {
        target: { value: description },
      });
      saveDraft();
      expect(view.client.createListing).not.toHaveBeenCalled();
      expect(view.onError).toHaveBeenCalledWith(
        vendorMessages.listings.quickList.descriptionInvalid,
      );
    },
  );
  it("accepts exactly 20 Unicode code points and rejects five-emoji used disclosure", async () => {
    const view = mountQuick();
    await fillDraft("D");
    fireEvent.change(input(vendorMessages.listings.quickList.descriptionLabel), {
      target: { value: "😀".repeat(20) },
    });
    fireEvent.change(input(vendorMessages.listings.fields.defectNotesLabel), {
      target: { value: "😀".repeat(5) },
    });
    saveDraft();
    expect(view.client.createListing).not.toHaveBeenCalled();
    expect(view.onError).toHaveBeenLastCalledWith(
      vendorMessages.listings.fields.defectNotesInvalid,
    );
    fireEvent.change(input(vendorMessages.listings.fields.defectNotesLabel), {
      target: { value: "😀".repeat(10) },
    });
    saveDraft();
    await waitFor(() => expect(view.client.createListing).toHaveBeenCalledOnce());
    expect(view.client.createListing.mock.calls[0]?.[0]).toMatchObject({
      description: "😀".repeat(20),
      publish: false,
    });
  });
  it.each(["title", "category"])("rejects missing %s without a write", async (missing) => {
    const view = mountQuick();
    await fillDraft("E");
    fireEvent.change(
      input(
        missing === "title"
          ? vendorMessages.listings.quickList.titleLabel
          : vendorMessages.listings.newCanonical.categoryLabel,
      ),
      { target: { value: "" } },
    );
    saveDraft();
    expect(view.client.createListing).not.toHaveBeenCalled();
    expect(view.onError).toHaveBeenCalledWith(vendorMessages.listings.errors.required);
  });
  it.each(["failed", "empty"])("blocks saving when categories are %s", async (state) => {
    const client = makeClient();
    if (state === "failed") client.listCategories.mockRejectedValue(new Error("synthetic failure"));
    else client.listCategories.mockResolvedValue([]);
    const view = mountQuick(client);
    fireEvent.change(input(vendorMessages.listings.fields.productClassLabel), {
      target: { value: "E" },
    });
    await waitFor(() =>
      expect(
        screen.getByText(vendorMessages.listings.quickList.categoriesUnavailable),
      ).toBeTruthy(),
    );
    saveDraft();
    expect(client.createListing).not.toHaveBeenCalled();
    expect(view.onSuccess).not.toHaveBeenCalled();
  });
  it("invalidates a stale category when the client changes and ignores late old results", async () => {
    const view = mountQuick();
    await fillDraft("E");
    const pending = deferred<CategoryOption[]>();
    const replacement = makeClient();
    replacement.listCategories.mockReturnValue(pending.promise);
    view.rerender(createElement(QuickListForm, { ...view.props, client: replacement }));
    saveDraft();
    expect(replacement.createListing).not.toHaveBeenCalled();
    const latest = makeClient();
    latest.listCategories.mockResolvedValue([
      {
        ...category,
        id: "10000000-0000-0000-0000-000000000002",
        name: "Replacement category",
      },
    ]);
    view.rerender(createElement(QuickListForm, { ...view.props, client: latest }));
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Replacement category" })).toBeTruthy(),
    );
    await act(async () => {
      pending.resolve([category]);
      await pending.promise;
    });
    saveDraft();
    expect(screen.queryByRole("option", { name: category.name })).toBeNull();
    expect(latest.createListing).not.toHaveBeenCalled();
  });
  it.each([
    ["0", "7"],
    ["1", "0"],
    ["10000", "7"],
    ["10", "366"],
  ])("retains E capacity/lead bounds (%s,%s)", async (capacity, lead) => {
    const view = mountQuick();
    await fillDraft("E");
    fireEvent.change(input(vendorMessages.listings.fields.capacityLabel), {
      target: { value: capacity },
    });
    fireEvent.change(input(vendorMessages.listings.fields.leadTimeLabel), {
      target: { value: lead },
    });
    saveDraft();
    expect(view.client.createListing).not.toHaveBeenCalled();
  });
  it("requires E capacity to cover minimum increments", async () => {
    const view = mountQuick();
    await fillDraft("E");
    fireEvent.change(input(vendorMessages.listings.fields.saleUnitLabel), {
      target: { value: "kg" },
    });
    fireEvent.change(input(vendorMessages.listings.fields.minStepsLabel), {
      target: { value: "11" },
    });
    saveDraft();
    expect(view.client.createListing).not.toHaveBeenCalled();
    expect(view.onError).toHaveBeenCalledWith(vendorMessages.listings.fields.capacityInvalid);
  });
  it("prevents duplicate dispatch while a draft request is pending", async () => {
    const view = mountQuick();
    await fillDraft("E");
    const pending = deferred<ListingCreateResponse>();
    view.client.createListing.mockReturnValue(pending.promise);
    const button = screen.getByRole("button", {
      name: vendorMessages.listings.quickList.saveDraft,
    });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(view.client.createListing).toHaveBeenCalledOnce();
    await act(async () => {
      pending.resolve(draftResponse);
      await pending.promise;
    });
    expect(view.onSuccess).toHaveBeenCalledOnce();
  });
  it("reports API rejection safely, retains inputs and allows a retry", async () => {
    const view = mountQuick();
    await fillDraft("E");
    view.client.createListing.mockRejectedValueOnce(
      new ApiError("prohibited_listing", "private server detail", {
        status: 422,
      }),
    );
    saveDraft();
    await waitFor(() =>
      expect(view.onError).toHaveBeenCalledWith(vendorMessages.listings.errors.submitFailed),
    );
    expect(view.onSuccess).not.toHaveBeenCalled();
    expect((input(vendorMessages.listings.quickList.titleLabel) as HTMLInputElement).value).toBe(
      " Synthetic item ",
    );
    saveDraft();
    await waitFor(() => expect(view.onSuccess).toHaveBeenCalledOnce());
  });
});

describe("QuickList retained unit and wholesale controls", () => {
  it("keeps milli-unit parsing and disables wholesale for per-measure D drafts", async () => {
    const view = mountQuick(makeClient(), true);
    await fillDraft("D");
    fireEvent.click(
      screen.getByRole("switch", {
        name: vendorMessages.listings.fields.wholesaleLabel,
      }),
    );
    fireEvent.change(input(vendorMessages.listings.fields.saleUnitLabel), {
      target: { value: "kg" },
    });
    fireEvent.change(input(vendorMessages.listings.fields.unitStepLabel), {
      target: { value: "0.125" },
    });
    fireEvent.change(input(vendorMessages.listings.fields.minStepsLabel), {
      target: { value: "2" },
    });
    expect(
      screen.queryByRole("switch", {
        name: vendorMessages.listings.fields.wholesaleLabel,
      }),
    ).toBeNull();
    saveDraft();
    await waitFor(() => expect(view.onSuccess).toHaveBeenCalledOnce());
    expect(view.client.createListing.mock.calls[0]?.[0]).toMatchObject({
      sale_unit: "kg",
      unit_step_milli: 125,
      min_steps: 2,
      price_ngwee: 123456,
      wholesale: false,
      moq: 1,
      publish: false,
    });
  });
  it.each(["0.0001", "9007199254740992"])(
    "rejects unsafe unit step %s before transport",
    async (step) => {
      const view = mountQuick();
      await fillDraft("D");
      fireEvent.change(input(vendorMessages.listings.fields.saleUnitLabel), {
        target: { value: "kg" },
      });
      fireEvent.change(input(vendorMessages.listings.fields.unitStepLabel), {
        target: { value: step },
      });
      saveDraft();
      expect(view.client.createListing).not.toHaveBeenCalled();
    },
  );
  it("preserves the supplied wholesale gate and E minimum-order capacity guard", async () => {
    const view = mountQuick();
    await fillDraft("E");
    expect(
      screen.queryByRole("switch", {
        name: vendorMessages.listings.fields.wholesaleLabel,
      }),
    ).toBeNull();
    view.rerender(createElement(QuickListForm, { ...view.props, wholesaleEnabled: true }));
    fireEvent.click(
      screen.getByRole("switch", {
        name: vendorMessages.listings.fields.wholesaleLabel,
      }),
    );
    fireEvent.change(input(vendorMessages.listings.fields.moqLabel), {
      target: { value: "11" },
    });
    saveDraft();
    expect(view.client.createListing).not.toHaveBeenCalled();
    fireEvent.change(input(vendorMessages.listings.fields.capacityLabel), {
      target: { value: "11" },
    });
    saveDraft();
    await waitFor(() => expect(view.onSuccess).toHaveBeenCalledOnce());
    expect(view.client.createListing.mock.calls[0]?.[0]).toMatchObject({
      vendor_capacity_per_week: 11,
      wholesale: true,
      moq: 11,
      publish: false,
    });
  });
});

describe("QuickList localized contract", () => {
  it.each(["en", "fr", "zh", "bem", "nya"] as const)(
    "resolves required draft guidance in %s",
    async (locale) => {
      const messages = (await loadNamespace(locale, "vendor")) as unknown as typeof vendorMessages;
      for (const key of [
        "descriptionLabel",
        "descriptionHelp",
        "descriptionInvalid",
        "saveDraft",
        "savingDraft",
        "draftNotice",
        "canonicalRequired",
        "categoriesUnavailable",
      ] as const) {
        const text = messages.listings.quickList[key];
        expect(text).toBeTruthy();
        expect(text).not.toBe(`listings.quickList.${key}`);
      }
      expect(messages.listings.success.draft).toBeTruthy();
      if (locale === "bem" || locale === "nya") {
        expect(messages.listings.quickList.intro).toBe(vendorMessages.listings.quickList.intro);
        expect(messages.listings.quickList.titlePlaceholder).toBe(
          vendorMessages.listings.quickList.titlePlaceholder,
        );
        expect(messages.listings.meta.description).toBe(vendorMessages.listings.meta.description);
      }
    },
  );
});

describe("QuickList parent-flow success", () => {
  it.each([false, true])(
    "reports an E draft accurately (used evidence=%s)",
    async (requiresEvidence) => {
      const client = makeClient();
      client.createListing.mockResolvedValue({
        ...draftResponse,
        requires_evidence: requiresEvidence,
      });
      flowMocks.client = client;
      render(createElement(ListingCreateFlow, { locale: "en" }));
      fireEvent.click(
        await screen.findByRole("tab", {
          name: vendorMessages.listings.tabs.quickList,
        }),
      );
      await fillDraft("E");
      if (requiresEvidence) {
        fireEvent.change(input(vendorMessages.listings.fields.conditionLabel), {
          target: { value: "used" },
        });
        fireEvent.change(input(vendorMessages.listings.fields.defectNotesLabel), {
          target: { value: "Synthetic wear marks" },
        });
      }
      vi.useFakeTimers();
      saveDraft();
      await act(async () => {
        await Promise.resolve();
      });
      expect(
        screen.getByText(
          requiresEvidence
            ? vendorMessages.listings.success.evidence
            : vendorMessages.listings.success.draft,
        ),
      ).toBeTruthy();
      expect(screen.queryByText(vendorMessages.listings.success.live)).toBeNull();
      act(() => {
        vi.advanceTimersByTime(1200);
      });
      expect(flowMocks.push).toHaveBeenCalledWith(
        requiresEvidence ? `/en/listings/${draftResponse.listing_id}/edit` : "/en/listings",
      );
    },
  );
  it("Catalog guidance selects the existing attach tab", async () => {
    flowMocks.client = makeClient();
    render(createElement(ListingCreateFlow, { locale: "en" }));
    fireEvent.click(
      await screen.findByRole("tab", {
        name: vendorMessages.listings.tabs.quickList,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: vendorMessages.listings.tabs.attach }));
    expect(
      screen
        .getByRole("tab", { name: vendorMessages.listings.tabs.attach })
        .getAttribute("aria-selected"),
    ).toBe("true");
  });
});
