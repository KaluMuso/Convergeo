// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.example${path}`,
}));
vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
import { RelatedProductRails } from "./related-product-rails";
const labels = {
  vendorHeading: "More from {vendor}",
  categoryHeading: "More in this category",
  loading: "Loading recommendations",
  unavailable: "Recommendations unavailable",
  vendorFallback: "Seller",
  noReviews: "No reviews yet",
  reviewCount: "({count})",
  quickAdd: "Add",
  wishlist: "Save",
  mediaEmpty: "No image",
};
const item = (slug: string) => ({
  slug,
  name: slug,
  listing_id: `offer-${slug}`,
  vendor_name: "Shop",
  from_price_ngwee: 1200,
  image_public_id: null,
});
const data = {
  product_slug: "current",
  listing_id: "source",
  vendor_name: "Shop",
  same_vendor: [item("vendor-product")],
  same_category: [item("category-product")],
};
const props = { locale: "en", slug: "current", listingId: "source", labels };
/** Legacy-path tests: /recommendations fails so the related-rails fallback runs. */
const railsOnly = (fetcher: (url: string, init?: unknown) => unknown) =>
  vi.fn((url: string, init?: unknown) =>
    url.includes("/recommendations")
      ? Promise.resolve({ ok: false, json: async () => ({}) })
      : fetcher(url, init),
  );
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RelatedProductRails", () => {
  it("shows distinct accessible rails and links to the exact priced offers without duplicates", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...data,
          same_category: [
            item("vendor-product"),
            item("current"),
            item("category-product"),
          ],
        }),
      }),
    );
    render(<RelatedProductRails {...props} />);
    expect(screen.getByRole("status")).toHaveTextContent(labels.loading);
    expect(
      await screen.findByRole("region", { name: "More from Shop" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: labels.categoryHeading }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(
      screen.getByRole("link", { name: /vendor-product/ }),
    ).toHaveAttribute(
      "href",
      "/en/p/vendor-product?listing=offer-vendor-product",
    );
    expect(screen.queryByText("current")).not.toBeInTheDocument();
  });
  it("hides both empty rails without inventing suggestions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ...data, same_vendor: [], same_category: [] }),
      }),
    );
    render(<RelatedProductRails {...props} />);
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it.each(["http", "network", "wrong-product", "wrong-seller"])(
    "degrades %s errors without stale cards",
    async (failure) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(async () => {
          if (failure === "network") throw new Error("offline");
          return {
            ok: failure !== "http",
            json: async () => ({
              ...data,
              product_slug: failure === "wrong-product" ? "wrong" : "current",
              listing_id: failure === "wrong-seller" ? "wrong" : "source",
            }),
          };
        }),
      );
      render(<RelatedProductRails {...props} />);
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent(
          labels.unavailable,
        ),
      );
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    },
  );
  it("removes old seller cards immediately and ignores late responses after switching", async () => {
    let oldResolve!: (value: unknown) => void;
    const old = new Promise((resolve) => {
      oldResolve = resolve;
    });
    // Route by seller: the first seller's response is held, the second resolves.
    const fetcher = vi.fn((url: string) =>
      url.includes("listing_id=second")
        ? Promise.resolve({
            ok: true,
            json: async () => ({
              ...data,
              listing_id: "second",
              vendor_name: "Second shop",
            }),
          })
        : old,
    );
    const routed = railsOnly(fetcher);
    vi.stubGlobal("fetch", routed);
    const view = render(<RelatedProductRails {...props} />);
    view.rerender(<RelatedProductRails {...props} listingId="second" />);
    await screen.findByRole("heading", { name: "More from Second shop" });
    await act(async () => {
      oldResolve({ ok: true, json: async () => data });
    });
    expect(
      screen.queryByRole("heading", { name: "More from Shop" }),
    ).not.toBeInTheDocument();
    expect(
      fetcher.mock.calls.some(([url]) =>
        String(url).includes("listing_id=second"),
      ),
    ).toBe(true);
    expect(routed).toHaveBeenCalled();
  });
  it("hides already rendered cards while a new seller request is pending", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => data })
      .mockReturnValueOnce(new Promise(() => {}));
    vi.stubGlobal("fetch", railsOnly(fetcher));
    const view = render(<RelatedProductRails {...props} />);
    await screen.findByRole("heading", { name: "More from Shop" });
    view.rerender(<RelatedProductRails {...props} listingId="second" />);
    expect(screen.getByRole("status")).toHaveTextContent(labels.loading);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("prefers /recommendations with store and category headings", async () => {
    const rec = (title: string) => ({
      id: `offer-${title}`,
      title,
      product_slug: title,
      vendor_name: "Shop",
      price_ngwee: 1500,
      image_public_id: null,
    });
    const fetcher = vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.includes("scope=store")
          ? { scope: "store", items: [rec("store-item")] }
          : { scope: "category", items: [rec("similar-item")] },
    }));
    vi.stubGlobal("fetch", fetcher);
    render(
      <RelatedProductRails
        {...props}
        labels={{
          ...labels,
          storeHeading: "More from this store",
          similarHeading: "Similar in this category",
        }}
      />,
    );
    expect(
      await screen.findByRole("region", { name: "More from this store" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Similar in this category" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /store-item/ })).toHaveAttribute(
      "href",
      "/en/p/store-item?listing=offer-store-item",
    );
    expect(
      fetcher.mock.calls.some(([url]) => String(url).includes("related-rails")),
    ).toBe(false);
  });
});
