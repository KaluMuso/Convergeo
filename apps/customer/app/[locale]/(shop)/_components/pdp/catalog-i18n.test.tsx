// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider, useTranslations } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

afterEach(() => {
  cleanup();
});

function CatalogIndicator() {
  const t = useTranslations("catalog");
  return <p data-testid="catalog-indicator">{t("pdp.gallery.indicator", { current: 1, total: 3 })}</p>;
}

describe("catalog client i18n provider", () => {
  it("does not render raw catalog.* keys when catalog messages are provided", () => {
    render(
      <NextIntlClientProvider
        locale="en"
        messages={{ catalog: catalogMessages }}
        onError={() => {}}
      >
        <CatalogIndicator />
      </NextIntlClientProvider>,
    );

    expect(screen.getByTestId("catalog-indicator")).toHaveTextContent("Image 1 of 3");
    expect(screen.queryByText("catalog.pdp.gallery.indicator")).not.toBeInTheDocument();
    expect(screen.queryByText("pdp.gallery.indicator")).not.toBeInTheDocument();
  });

  it("raw key appears only when the catalog namespace is missing (regression guard)", () => {
    render(
      <NextIntlClientProvider locale="en" messages={{}} onError={() => {}}>
        <CatalogIndicator />
      </NextIntlClientProvider>,
    );

    // next-intl falls back to the namespaced key path when messages are absent.
    expect(screen.getByTestId("catalog-indicator").textContent).toMatch(/gallery\.indicator/);
  });
});
