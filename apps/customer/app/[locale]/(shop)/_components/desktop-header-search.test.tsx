// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request }),
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.com",
}));

const usePathname = vi.fn(() => "/en");

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => usePathname(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { DesktopHeaderSearch } from "./desktop-header-search";

const labels = {
  placeholder: "Search Vergeo5",
  submit: "Search",
  ariaLabel: "Search",
  suggestionsLabel: "Search suggestions",
  noSuggestions: "No suggestions",
  recentTitle: "Recent searches",
};

describe("DesktopHeaderSearch", () => {
  beforeEach(() => {
    usePathname.mockReturnValue("/en");
    request.mockResolvedValue({
      query: "phone",
      suggestions: [{ title: "Itel A70", entity_kind: "product", entity_id: "1" }],
    });
  });

  it("renders nothing on the search results page", () => {
    usePathname.mockReturnValue("/en/search");
    const { container } = render(<DesktopHeaderSearch locale="en" labels={labels} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the combobox on non-search shop routes", () => {
    usePathname.mockReturnValue("/en");
    render(<DesktopHeaderSearch locale="en" labels={labels} />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("opens a suggestion listbox after typing", async () => {
    const user = userEvent.setup();
    render(<DesktopHeaderSearch locale="en" labels={labels} />);

    await user.type(screen.getByRole("combobox"), "phone");

    await waitFor(() => {
      expect(screen.getByRole("listbox", { name: "Search suggestions" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: /Itel A70/i })).toBeInTheDocument();
  });
});
