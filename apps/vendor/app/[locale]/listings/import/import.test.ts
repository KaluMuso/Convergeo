import { afterEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { applyRawRows, previewCsv } from "./_lib/import-client";

function mockFetchOnce(payload: unknown, ok = true, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(payload),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("import i18n", () => {
  it("exposes the preview + apply namespace keys used by the flow", () => {
    expect(vendorMessages.listings.import.preview.previewButton).toBeTruthy();
    expect(vendorMessages.listings.import.preview.suggestionsLabel).toBeTruthy();
    expect(vendorMessages.listings.import.preview.attachAction).toContain("{name}");
    expect(vendorMessages.listings.import.apply.button).toBeTruthy();
    expect(vendorMessages.listings.import.errors.previewFailed).toBeTruthy();
  });
});

describe("applyRawRows", () => {
  it("POSTs raw_rows as JSON to /listings/import and parses the summary", async () => {
    const fetchMock = mockFetchOnce({ accepted: 1, rejected: 0, rows: [] });
    const summary = await applyRawRows(
      [{ sku: "A-1", title: "Thing", price_ngwee: "1000", product_id: "p-1" }],
      () => "tok",
    );

    expect(summary.accepted).toBe(1);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/listings/import");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.raw_rows[0].product_id).toBe("p-1");
  });
});

describe("previewCsv", () => {
  it("POSTs the CSV text to /listings/import/preview and returns suggestions", async () => {
    const fetchMock = mockFetchOnce({
      total: 1,
      valid: 1,
      invalid: 0,
      rows: [
        {
          row: 1,
          ok: true,
          errors: [],
          sku: "A-1",
          title: "Itel A70",
          price_ngwee: 1000,
          product_id: null,
          matched_name: null,
          suggestions: [{ product_id: "p-1", name: "Itel A70 Smartphone", score: 0.9 }],
          raw: { sku: "A-1", title: "Itel A70" },
        },
      ],
    });
    // jsdom's File lacks .text() in this env; a minimal stub is all previewCsv uses.
    const file = {
      text: () => Promise.resolve("sku,title\nA-1,Itel A70\n"),
    } as unknown as File;
    const preview = await previewCsv(file, () => "tok");

    expect(preview.rows[0]?.suggestions[0]?.product_id).toBe("p-1");
    const url = fetchMock.mock.calls[0]?.[0];
    expect(String(url)).toContain("/listings/import/preview");
  });
});
