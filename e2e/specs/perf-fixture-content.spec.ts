import { chromium, expect, test } from "@playwright/test";

/** Actual browser fetches under the built app's CSP, TLS trust and CORS policy. */
test("disposable catalogue and PDP contain the committed seeded product", async ({
  page,
  browser,
}, testInfo) => {
  expect(process.env.GITHUB_ACTIONS).toBe("true");
  expect(process.env.E2E_BASE_URL).toBe("http://localhost:3000");
  expect(process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE).toBe("preview");
  const api = new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "");
  expect(api.protocol).toBe("https:");
  expect(api.hostname).toBe(process.env.PERF_FIXTURE_API_HOST);
  expect(api.port).toBe("8000");
  const octets = api.hostname.split(".").map(Number);
  const privateBridge =
    octets.length === 4 &&
    octets.every((part) => Number.isInteger(part) && part >= 0 && part <= 255) &&
    (octets[0] === 10 ||
      (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
      (octets[0] === 192 && octets[1] === 168));
  expect(privateBridge).toBe(true);
  expect(api.username + api.password + api.search + api.hash).toBe("");
  const supabase = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "");
  expect(supabase.origin).toBe("http://127.0.0.1:54321");
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
  // Assert the role without placing the key in a matcher failure or artifact.
  let anonymousRole = false;
  try {
    anonymousRole =
      JSON.parse(Buffer.from(anonKey.split(".")[1] ?? "", "base64url").toString()).role === "anon";
  } catch {
    // Invalid input is a hard failure below, never a skipped acceptance.
  }
  expect(anonymousRole).toBe(true);

  const evidence: Array<Record<string, unknown>> = [];
  try {
    evidence.push({
      event: "browser",
      playwrightVersion: testInfo.config.version,
      browserVersion: browser.version(),
      managedExecutablePath: chromium.executablePath(),
      configuredExecutablePath: testInfo.project.use.launchOptions?.executablePath,
      chromiumSandbox: testInfo.project.use.launchOptions?.chromiumSandbox,
      ignoreHTTPSErrors: testInfo.project.use.ignoreHTTPSErrors,
      bypassCSP: testInfo.project.use.bypassCSP,
    });
    expect(testInfo.config.version).toBe("1.56.1");
    expect(browser.version()).toMatch(/^141\./);
    expect(testInfo.project.use.launchOptions?.executablePath).toBe(chromium.executablePath());
    expect(testInfo.project.use.launchOptions?.chromiumSandbox).toBe(true);
    expect(testInfo.project.use.ignoreHTTPSErrors).toBe(false);
    expect(testInfo.project.use.bypassCSP).toBe(false);

    const categoryDocument = await page.goto("/en/c/electronics");
    expect(categoryDocument?.status()).toBe(200);
    expect(categoryDocument?.headers()["content-security-policy"]).toContain(
      "upgrade-insecure-requests",
    );
    expect(new URL(page.url()).origin).toBe("http://localhost:3000");

    const contract = await page.evaluate(
      async ({ apiOrigin, supabaseOrigin, anon }) => {
        const options: RequestInit = { credentials: "omit", cache: "no-store", redirect: "error" };
        // A protected read must refuse the same anonymous browser before public acceptance.
        const wishlist = await fetch(`${apiOrigin}/account/wishlist`, options);
        const productResponse = await fetch(`${apiOrigin}/products/smartphone-x1`, options);
        const product = await productResponse.json();
        const catalogResponse = await fetch(
          `${apiOrigin}/catalog/listings?category_path=electronics`,
          options,
        );
        const catalog = await catalogResponse.json();
        const categoriesResponse = await fetch(
          `${supabaseOrigin}/rest/v1/categories?select=slug,name&slug=eq.electronics`,
          { ...options, headers: { apikey: anon, Authorization: `Bearer ${anon}` } },
        );
        const categories = await categoriesResponse.json();
        // Only contract booleans/counts leave the browser; no body, key or headers.
        return {
          wishlistStatus: wishlist.status,
          productStatus: productResponse.status,
          productSlugMatches: product.slug === "smartphone-x1",
          productNameMatches: product.name === "Smartphone X1",
          listingCount: product.listing_count,
          catalogStatus: catalogResponse.status,
          catalogTotal: catalog.total,
          catalogContainsProduct:
            Array.isArray(catalog.items) &&
            catalog.items.some(
              (item: { product_slug?: string }) => item.product_slug === "smartphone-x1",
            ),
          categoriesStatus: categoriesResponse.status,
          electronicsPresent:
            Array.isArray(categories) &&
            categories.some(
              (item: { slug?: string; name?: string }) =>
                item.slug === "electronics" && item.name === "Electronics",
            ),
        };
      },
      { apiOrigin: api.origin, supabaseOrigin: supabase.origin, anon: anonKey },
    );
    evidence.push({ event: "browser-read-contract", ...contract });
    expect([401, 403]).toContain(contract.wishlistStatus);
    expect(contract.productStatus).toBe(200);
    expect(contract.productSlugMatches).toBe(true);
    expect(contract.productNameMatches).toBe(true);
    expect(contract.listingCount).toBeGreaterThan(0);
    expect(contract.catalogStatus).toBe(200);
    expect(contract.catalogTotal).toBeGreaterThan(0);
    expect(contract.catalogContainsProduct).toBe(true);
    expect(contract.categoriesStatus).toBe(200);
    expect(contract.electronicsPresent).toBe(true);

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
    await expect(page.getByTestId("pdp-seller-count")).toHaveText(
      `${contract.listingCount} seller${contract.listingCount === 1 ? "" : "s"}`,
    );
    await page.screenshot({ path: testInfo.outputPath("product.png"), fullPage: true });

    const negativePage = await page.context().newPage();
    const cdp = await page.context().newCDPSession(negativePage);
    const negativeUrl = `${api.origin}/catalog/listings?category_path=electronics`;
    let requestId = "";
    let actualRequestOrigin = false;
    let apiResponseStatus = 0;
    let corsError = "";
    let rejected = false;
    const origins = new Map<string, boolean>();
    const statuses = new Map<string, number>();
    const corsErrors = new Map<string, string>();
    const isNegativeOrigin = (headers: Record<string, unknown>) =>
      Object.entries(headers).some(
        ([key, value]) => key.toLowerCase() === "origin" && value === "http://127.0.0.1:3000",
      );
    const updateMatchedRequest = () => {
      actualRequestOrigin = origins.get(requestId) ?? false;
      apiResponseStatus = statuses.get(requestId) ?? 0;
      corsError = corsErrors.get(requestId) ?? "";
    };
    await cdp.send("Network.enable");
    cdp.on("Network.requestWillBeSent", (event) => {
      if (event.request.url === negativeUrl) {
        requestId = event.requestId;
        origins.set(
          requestId,
          Boolean(origins.get(requestId)) || isNegativeOrigin(event.request.headers),
        );
        updateMatchedRequest();
      }
    });
    cdp.on("Network.responseReceivedExtraInfo", (event) => {
      statuses.set(event.requestId, event.statusCode);
      updateMatchedRequest();
    });
    cdp.on("Network.requestWillBeSentExtraInfo", (event) => {
      origins.set(
        event.requestId,
        Boolean(origins.get(event.requestId)) || isNegativeOrigin(event.headers),
      );
      updateMatchedRequest();
    });
    cdp.on("Network.loadingFailed", (event) => {
      corsErrors.set(event.requestId, event.corsErrorStatus?.corsError ?? "");
      updateMatchedRequest();
    });
    try {
      const negativeDocument = await negativePage.goto("http://127.0.0.1:3000/en/c/electronics");
      expect(negativeDocument?.status()).toBe(200);
      expect(negativeDocument?.headers()["content-security-policy"]).toContain(
        "upgrade-insecure-requests",
      );
      rejected = await negativePage.evaluate(async (url) => {
        try {
          await fetch(url, { credentials: "omit", cache: "no-store", redirect: "error" });
          return false;
        } catch {
          return true;
        }
      }, negativeUrl);
      await expect.poll(() => apiResponseStatus).toBe(200);
      await expect
        .poll(() => corsError)
        .toMatch(/^(MissingAllowOriginHeader|AllowOriginMismatch)$/);
      expect(actualRequestOrigin).toBe(true);
      expect(rejected).toBe(true);
    } finally {
      evidence.push({
        event: "browser-cors-negative",
        rejected,
        apiResponseStatus,
        actualRequestOrigin,
        corsError,
      });
      try {
        await cdp.detach();
      } finally {
        await negativePage.close();
      }
    }
  } finally {
    await testInfo.attach("fixture-contract", {
      body: JSON.stringify(evidence, null, 2),
      contentType: "application/json",
    });
  }
});
