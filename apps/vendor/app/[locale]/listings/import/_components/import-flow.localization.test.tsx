import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";

import bem from "../../../../../../../packages/i18n/messages/bem/vendor.json";
import en from "../../../../../../../packages/i18n/messages/en/vendor.json";
import fr from "../../../../../../../packages/i18n/messages/fr/vendor.json";
import nya from "../../../../../../../packages/i18n/messages/nya/vendor.json";
import zh from "../../../../../../../packages/i18n/messages/zh/vendor.json";
import { deepMergeMessages } from "../../../../../../../packages/i18n/src/deep-merge";

import { ImportFlow } from "./import-flow";

const mocks = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn() }));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "test-token" },
    loading: false,
  }),
}));
vi.mock("../_lib/import-client", () => ({
  previewCsv: mocks.preview,
  applyRawRows: mocks.apply,
  downloadTemplateCsv: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

for (const [locale, messages] of Object.entries({ en, fr, zh, bem, nya })) {
  it(`renders safe import errors through the ${locale} locale catalog`, async () => {
    const codes = ["invalidInteger", "duplicateSku", "canonicalRequired", "databaseFailure"];
    mocks.preview.mockResolvedValue({
      total: 5,
      valid: 0,
      invalid: 5,
      rows: [
        ...codes.map((code) => `listings.import.errors.${code}`),
        "SQL private_table ERROR",
      ].map((error, index) => ({
        row: index + 1,
        ok: false,
        errors: [error],
        title: `Item ${index}`,
        product_id: null,
        suggestions: [],
        raw: { sku: `SKU-${index}` },
      })),
    });
    render(
      <NextIntlClientProvider
        locale={locale}
        timeZone="Africa/Lusaka"
        messages={{
          vendor: { listings: deepMergeMessages(en, messages).listings },
        }}
      >
        <ImportFlow />
      </NextIntlClientProvider>,
    );
    fireEvent.change(screen.getByLabelText(messages.listings.import.upload.fileLabel), {
      target: {
        files: [new File(["csv"], "items.csv", { type: "text/csv" })],
      },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: messages.listings.import.preview.previewButton,
      }),
    );
    for (const code of codes) {
      await screen.findByText(
        messages.listings.import.errors[code as keyof typeof messages.listings.import.errors],
      );
    }
    await screen.findByText(messages.listings.import.errors.unknownError);
    expect(screen.queryByText("SQL private_table ERROR")).toBeNull();
    expect(
      screen
        .getByRole("button", { name: messages.listings.import.apply.button })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(mocks.apply).not.toHaveBeenCalled();
    if (locale === "bem" || locale === "nya") {
      expect(messages.listings.import.errors.canonicalRequired).toBe(
        en.listings.import.errors.canonicalRequired,
      );
    }
  });
}

it("requires catalogue selection before applying a new SKU and sends the selected product", async () => {
  const raw = {
    sku: "NEW-SKU",
    title: "Rice",
    price_ngwee: "1000",
    product_id: "",
  };
  mocks.preview.mockResolvedValue({
    total: 1,
    valid: 0,
    invalid: 1,
    rows: [
      {
        row: 1,
        ok: false,
        errors: ["listings.import.errors.canonicalRequired"],
        title: "Rice",
        product_id: null,
        suggestions: [{ product_id: "active-product", name: "Rice", score: 1 }],
        raw,
      },
    ],
  });
  mocks.apply.mockResolvedValue({ accepted: 1, rejected: 0, rows: [] });
  render(
    <NextIntlClientProvider
      locale="en"
      timeZone="Africa/Lusaka"
      messages={{ vendor: { listings: en.listings } }}
    >
      <ImportFlow />
    </NextIntlClientProvider>,
  );
  fireEvent.change(screen.getByLabelText(en.listings.import.upload.fileLabel), {
    target: { files: [new File(["csv"], "items.csv", { type: "text/csv" })] },
  });
  fireEvent.click(
    screen.getByRole("button", {
      name: en.listings.import.preview.previewButton,
    }),
  );
  const apply = await screen.findByRole("button", {
    name: en.listings.import.apply.button,
  });
  expect(apply.hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Attach: Rice" }));
  await waitFor(() => expect(apply.hasAttribute("disabled")).toBe(false));
  expect(screen.queryByText(en.listings.import.errors.canonicalRequired)).toBeNull();
  fireEvent.click(apply);
  await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
  expect(mocks.apply.mock.calls[0]?.[0]).toEqual([{ ...raw, product_id: "active-product" }]);
});
