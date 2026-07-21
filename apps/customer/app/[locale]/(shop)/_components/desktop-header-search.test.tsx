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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
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
};

describe("DesktopHeaderSearch", () => {
  beforeEach(() => {
    request.mockResolvedValue({
      query: "phone",
      suggestions: [{ title: "Itel A70", entity_kind: "product", entity_id: "1" }],
    });
  });

  it("opens a suggestion listbox after typing", async () => {
    const user = userEvent.setup();
    render(<DesktopHeaderSearch locale="en" labels={labels} />);

    await user.type(screen.getByRole("searchbox"), "phone");

    await waitFor(() => {
      expect(screen.getByRole("listbox", { name: "Search suggestions" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: /Itel A70/i })).toBeInTheDocument();
  });
});
