import { afterEach, describe, expect, it, vi } from "vitest";

import { createManageClient } from "./manage-client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createManageClient.countInReview", () => {
  it("reads the narrow count endpoint instead of the full listing list", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ count: 3 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const count = await createManageClient(() => "token").countInReview();

    expect(count).toBe(3);
    const calls = fetchMock.mock.calls as unknown as Array<[string | URL | Request]>;
    expect(String(calls[0]?.[0])).toMatch(/\/vendor\/listings\/in-review-count$/);
  });
});
