import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import marketing from "../../../../packages/i18n/messages/en/marketing.json";

afterEach(cleanup);

vi.mock("next/navigation", () => ({
  useParams: () => ({ locale: "en" }),
}));

import ErrorBoundary from "./error";
import NotFound from "./not-found";

describe("marketing 404 / 500 messages", () => {
  it("expose branded copy and recovery links", () => {
    expect(marketing.notFound.code).toBe("404");
    expect(marketing.notFound.home.length).toBeGreaterThan(0);
    expect(marketing.notFound.search.length).toBeGreaterThan(0);
    expect(marketing.error.code).toBe("500");
    expect(marketing.error.retry.length).toBeGreaterThan(0);
  });
});

describe("500 error boundary", () => {
  it("renders branded content with retry and recovery links", () => {
    render(<ErrorBoundary reset={() => undefined} />);
    expect(screen.getByText(marketing.error.heading)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: marketing.error.retry })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: marketing.error.home })).toHaveAttribute("href", "/en");
    expect(screen.getByRole("link", { name: marketing.error.help })).toHaveAttribute(
      "href",
      "/en/help",
    );
  });
});

describe("404 not-found page", () => {
  it("renders branded content with home / search / help recovery links", async () => {
    render(await NotFound());
    expect(screen.getByText(marketing.notFound.heading)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: marketing.notFound.home })).toHaveAttribute(
      "href",
      "/en",
    );
    expect(screen.getByRole("link", { name: marketing.notFound.search })).toHaveAttribute(
      "href",
      "/en/search",
    );
    expect(screen.getByRole("link", { name: marketing.notFound.help })).toHaveAttribute(
      "href",
      "/en/help",
    );
  });
});
