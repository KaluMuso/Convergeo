// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import marketing from "../../../../../packages/i18n/messages/en/marketing.json";

import CheckoutLoading from "./checkout/loading";
import DealsLoading from "./deals/loading";
import EventDetailLoading from "./e/[slug]/loading";
import ShopError from "./error";
import EventsLoading from "./events/loading";
import ServiceDetailLoading from "./s/[slug]/loading";
import VendorDetailLoading from "./v/[slug]/loading";
import WishlistLoading from "./wishlist/loading";

vi.mock("next/navigation", () => ({ useParams: () => ({ locale: "en" }) }));
vi.mock("@vergeo/observability", () => ({ useReportClientError: vi.fn() }));

afterEach(cleanup);

describe("shop route skeletons", () => {
  it.each([
    ["events-loading", EventsLoading],
    ["deals-loading", DealsLoading],
    ["wishlist-loading", WishlistLoading],
    ["checkout-loading", CheckoutLoading],
    ["event-detail-loading", EventDetailLoading],
    ["service-detail-loading", ServiceDetailLoading],
    ["vendor-detail-loading", VendorDetailLoading],
  ] as const)("%s renders an aria-hidden, string-free placeholder", (id, Component) => {
    const { container } = render(<Component />);
    const root = screen.getByTestId(id);
    expect(root).toHaveAttribute("aria-hidden", "true");
    expect(container.textContent).toBe("");
  });
});

describe("shop error boundary", () => {
  it("keeps recovery actions and retries via reset", () => {
    const reset = vi.fn();
    render(<ShopError error={new Error("boom")} reset={reset} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: marketing.error.retry }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: marketing.error.home })).toHaveAttribute("href", "/en");
  });
});
