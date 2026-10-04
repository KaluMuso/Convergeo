import { readFile } from "node:fs/promises";

import { describe, expect, it, vi } from "vitest";

import { handleCiPerfMedia } from "./ci-perf-media";

import type { CiPerfServerEnv } from "./ci-perf-harness";

const env: CiPerfServerEnv = {
  CI: "true",
  GITHUB_ACTIONS: "true",
  CI_PERF_HARNESS: "1",
  NEXT_PUBLIC_CI_PERF_HARNESS: "1",
  NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
  NEXT_PUBLIC_SITE_URL: "http://localhost:3000",
  NEXT_PUBLIC_API_BASE_URL: "http://10.1.2.3:8000",
  CI_PERF_UPSTREAM_ORIGIN: "http://10.1.2.3:8000",
  NODE_ENV: "production",
  ENV: "development",
  SUPABASE_URL: "http://127.0.0.1:54321",
};

describe("closed CI media endpoint", () => {
  it("serves only the exact owned fixture variant with image type and no cache", async () => {
    const read = vi
      .fn()
      .mockResolvedValue(Buffer.from("RIFFfixtureWEBP")) as unknown as typeof readFile;
    const response = await handleCiPerfMedia(
      new Request("http://localhost:3000/api/ci-perf-media?width=720"),
      env,
      read,
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/webp");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(read).toHaveBeenCalledWith(
      expect.stringContaining("ci-fixtures/smartphone-x1-720.webp"),
    );
  });
  for (const suffix of [
    "",
    "?width=999",
    "?width=../secret",
    "?width=720&width=360",
    "?width=720&path=secret",
    "/secret?width=720",
  ]) {
    it(`rejects unsupported media request ${suffix}`, async () => {
      const read = vi.fn() as unknown as typeof readFile;
      expect(
        (
          await handleCiPerfMedia(
            new Request(`http://localhost:3000/api/ci-perf-media${suffix}`),
            env,
            read,
          )
        ).status,
      ).toBe(404);
      expect(read).not.toHaveBeenCalled();
    });
  }
  it("does not read a file outside the harness, on another origin, or for mutations", async () => {
    const read = vi.fn() as unknown as typeof readFile;
    expect(
      (
        await handleCiPerfMedia(
          new Request("http://localhost:3000/api/ci-perf-media?width=720"),
          { ...env, CI: "false" },
          read,
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await handleCiPerfMedia(
          new Request("http://other.test/api/ci-perf-media?width=720"),
          env,
          read,
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await handleCiPerfMedia(
          new Request("http://localhost:3000/api/ci-perf-media?width=720", { method: "POST" }),
          env,
          read,
        )
      ).status,
    ).toBe(405);
    expect(read).not.toHaveBeenCalled();
  });
});
