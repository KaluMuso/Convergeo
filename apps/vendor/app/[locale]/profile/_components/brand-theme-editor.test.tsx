// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { contrastRatio } from "@vergeo/ui/src/brand-theme";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../../../../../../packages/i18n/messages/en/vendor.json";

import { BrandThemeEditor } from "./brand-theme-editor";

afterEach(cleanup);

function renderEditor(onChange = vi.fn(), logoUrl: string | null = null) {
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor: en }}>
      <BrandThemeEditor
        value={{ primary: null, accent: null }}
        onChange={onChange}
        logoUrl={logoUrl}
      />
    </NextIntlClientProvider>,
  );
  return onChange;
}

describe("BrandThemeEditor", () => {
  it("clamps a too-light primary to AA as it is picked", () => {
    const onChange = renderEditor();
    fireEvent.change(screen.getByLabelText("Primary colour"), { target: { value: "#ffe066" } });
    const next = onChange.mock.calls.at(-1)?.[0] as { primary: string };
    expect(contrastRatio(next.primary, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("disables logo extraction until a logo exists", () => {
    renderEditor();
    expect(screen.getByTestId("brand-extract")).toBeDisabled();
    expect(screen.getByText("Upload a logo first.")).toBeInTheDocument();
  });
});
