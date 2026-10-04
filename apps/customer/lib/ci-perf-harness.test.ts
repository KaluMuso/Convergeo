import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ciPerfMediaUrl,
  ciPerfPublicEnabled,
  isCiPerfUpstream,
} from "../../../packages/ui/src/media/ci-perf-fixture";

import { getApiBaseUrl, resolveApiBaseUrl } from "./api-base-url";
import { assertCiPerfBuild, ciPerfServerEnabled, type CiPerfServerEnv } from "./ci-perf-harness";

export const harness: CiPerfServerEnv = {
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

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("disposable CI activation", () => {
  it("accepts the exact isolated context", () => {
    expect(ciPerfServerEnabled(harness)).toBe(true);
    expect(ciPerfPublicEnabled(harness)).toBe(true);
  });
  for (const key of Object.keys(harness) as Array<keyof CiPerfServerEnv>) {
    it(`closes when ${key} is absent`, () =>
      expect(ciPerfServerEnabled({ ...harness, [key]: undefined })).toBe(false));
  }
  for (const overrides of [
    { VERCEL: "1" },
    { VERCEL_ENV: "preview" },
    { NEXT_PUBLIC_DEPLOYMENT_PLANE: "production" },
    { NEXT_PUBLIC_DEPLOYMENT_PLANE: "staging" },
    { NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000" },
    { NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com" },
    { CI_PERF_UPSTREAM_ORIGIN: "http://10.1.2.4:8000" },
  ]) {
    it(`rejects divergent or deployed context ${JSON.stringify(overrides)}`, () =>
      expect(ciPerfServerEnabled({ ...harness, ...overrides })).toBe(false));
  }
  it("validates canonical RFC1918 origins without aliases or extra URL components", () => {
    for (const origin of [
      "http://10.1.2.3:8000",
      "http://172.16.2.3:8000",
      "http://192.168.2.3:8000",
    ])
      expect(isCiPerfUpstream(origin)).toBe(true);
    for (const origin of [
      "http://127.0.0.2:8000",
      "http://172.32.2.3:8000",
      "http://10.1.2.256:8000",
      "http://010.1.2.3:8000",
      "http://10.1.2.3:8000/",
      "http://x@10.1.2.3:8000",
      "https://10.1.2.3:8000",
      "http://10.1.2.3:8001",
    ])
      expect(isCiPerfUpstream(origin)).toBe(false);
  });
  it("fails a flagged ordinary build and leaves an ordinary unflagged build untouched", () => {
    vi.stubEnv("NEXT_PUBLIC_CI_PERF_HARNESS", "1");
    expect(() => assertCiPerfBuild()).toThrow(/isolated/);
    vi.stubEnv("NEXT_PUBLIC_CI_PERF_HARNESS", "");
    expect(() => assertCiPerfBuild()).not.toThrow();
  });
  it("routes only the admitted CI browser through the explicit BFF; SSR retains upstream", () => {
    for (const [key, value] of Object.entries(harness)) vi.stubEnv(key, value as string);
    vi.stubGlobal("window", { location: { origin: "http://localhost:3000" } });
    expect(resolveApiBaseUrl()).toBe("http://10.1.2.3:8000");
    expect(getApiBaseUrl()).toBe("http://localhost:3000/api/ci-perf");
    vi.stubGlobal("window", undefined);
    expect(getApiBaseUrl()).toBe("http://10.1.2.3:8000");
    vi.stubGlobal("window", { location: { origin: "https://customer.example.test" } });
    expect(getApiBaseUrl()).toBe("http://10.1.2.3:8000");
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "");
    expect(getApiBaseUrl()).toBe("");
  });
  it("maps exactly one CI fixture publicId, never demo or arbitrary IDs", () => {
    for (const [key, value] of Object.entries(harness)) vi.stubEnv(key, value as string);
    expect(ciPerfMediaUrl("ci-perf/smartphone-x1", 720)).toBe("/api/ci-perf-media?width=720");
    expect(ciPerfMediaUrl("vergeo5/demo/phone-a", 720)).toBeNull();
    expect(ciPerfMediaUrl("ci-perf/../smartphone-x1", 720)).toBeNull();
    expect(() => ciPerfMediaUrl("ci-perf/smartphone-x1", 999)).toThrow();
    vi.stubEnv("NEXT_PUBLIC_DEPLOYMENT_PLANE", "production");
    expect(ciPerfMediaUrl("ci-perf/smartphone-x1", 720)).toBeNull();
  });
});
