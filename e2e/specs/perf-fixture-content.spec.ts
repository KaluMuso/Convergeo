import { expect, test } from "@playwright/test";

/** Runs only against the existing runner-local server, before Lighthouse. */
test("disposable catalogue and PDP contain the committed seeded product", async ({
  page,
  request,
}, testInfo) => {
  expect(process.env.E2E_BASE_URL).toBe("http://localhost:3000");
  const api = new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "");
  expect(api.protocol).toBe("http:");
  expect(api.hostname).toBe(process.env.PERF_FIXTURE_API_HOST);
  expect(api.port).toBe("8000");
  expect(process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE).toBe("preview");

  const evidence: Array<Record<string, unknown>> = [];
  const pending = new Map<object, string>();
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.origin === "http://localhost:3000" || url.origin === api.origin)
      pending.set(req, `${req.method()} ${url.origin}${url.pathname}`);
  });
  const completed = (req: { url(): string; method(): string }) => {
    pending.delete(req);
  };
  page.on("requestfinished", completed);
  page.on("requestfailed", completed);
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (
      (url.origin === "http://localhost:3000" || url.origin === api.origin) &&
      ["/cart", "/catalog/listings", "/products/smartphone-x1"].includes(url.pathname)
    ) {
      evidence.push({
        event: "response",
        path: url.pathname,
        origin: url.origin,
        status: response.status(),
        contentType: response.headers()["content-type"],
      });
    }
  });

  try {
    const productResponse = await request.get(`${api.origin}/products/smartphone-x1`);
    expect(productResponse.status()).toBe(200);
    const product = await productResponse.json();
    evidence.push({
      event: "product-contract",
      status: productResponse.status(),
      slug: product.slug,
      name: product.name,
      listingCount: product.listing_count,
    });
    expect(product.slug).toBe("smartphone-x1");
    expect(product.name).toBe("Smartphone X1");
    expect(product.listing_count).toBeGreaterThan(0);

    const catalogResponse = await request.get(
      `${api.origin}/catalog/listings?category_path=electronics`,
    );
    expect(catalogResponse.status()).toBe(200);
    const catalog = await catalogResponse.json();
    const phone = catalog.items?.find(
      (item: { product_slug?: string }) => item.product_slug === "smartphone-x1",
    );
    evidence.push({
      event: "category-contract",
      status: catalogResponse.status(),
      total: catalog.total,
      expectedProductPresent: Boolean(phone),
    });
    expect(catalog.total).toBeGreaterThan(0);
    expect(phone).toBeTruthy();

    await page.goto("/en/c/electronics");
    await expect(page.getByTestId("plp-unavailable")).toHaveCount(0);
    await expect(
      page.getByTestId("listing-grid").locator('a[href="/en/p/smartphone-x1"]').first(),
    ).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("category.png"), fullPage: true });

    await page.goto("/en/p/smartphone-x1");
    await expect(page.getByTestId("pdp-unavailable")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { level: 1, name: "Smartphone X1", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("pdp-seller-count")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("product.png"), fullPage: true });
  } finally {
    evidence.push({ event: "completion", pending: [...pending.values()] });
    await testInfo.attach("fixture-contract", {
      body: JSON.stringify(evidence, null, 2),
      contentType: "application/json",
    });
  }
});
