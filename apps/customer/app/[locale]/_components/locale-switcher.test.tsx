import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleSwitcher } from "./locale-switcher";

const assign = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/search",
}));

const labels = {
  ariaLabel: "Choose language",
  names: {
    en: "English",
    bem: "Bemba",
    nya: "Nyanja",
    fr: "French",
  },
};

describe("LocaleSwitcher", () => {
  beforeEach(() => {
    cleanup();
    assign.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign },
    });
  });

  it("lists public locales only", () => {
    render(<LocaleSwitcher locale="en" labels={labels} />);

    expect(screen.getAllByRole("option").map((option) => option.getAttribute("value"))).toEqual([
      "en",
      "bem",
      "nya",
      "fr",
    ]);
  });

  it("renders shop variant with surface styling", () => {
    render(<LocaleSwitcher locale="en" labels={labels} variant="shop" />);

    const select = screen.getByTestId("locale-switcher");
    expect(select.className).toContain("bg-surface");
  });

  it("navigates to the same route under the new locale", async () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign, search: "?q=phone" },
    });

    const user = userEvent.setup();
    render(<LocaleSwitcher locale="en" labels={labels} />);

    await user.selectOptions(screen.getByTestId("locale-switcher"), "bem");

    expect(assign).toHaveBeenCalledWith("/bem/search?q=phone");
  });
});
