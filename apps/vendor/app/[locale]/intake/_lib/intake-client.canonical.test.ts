import { afterEach, expect, it, vi } from "vitest";

import { createIntakeClient } from "./intake-client";

vi.mock("../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));
afterEach(() => vi.unstubAllGlobals());

it("sends the vendor-selected canonical identity in the authenticated submit request", async () => {
  const result = {
    session_id: "intake session",
    listing_id: "draft-listing",
    listing_status: "draft",
    session_status: "pending_admin_review",
    already_submitted: false,
  };
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => result,
  });
  vi.stubGlobal("fetch", fetchMock);
  const productId = "44444444-4444-4444-8444-444444444444";
  const client = createIntakeClient(() => "synthetic-test-token");
  expect(await client.submit("intake session", productId)).toEqual(result);
  expect(fetchMock).toHaveBeenCalledOnce();
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("https://api.example.test/vendor/intake/sessions/intake%20session/submit");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ product_id: productId });
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer synthetic-test-token");
});
