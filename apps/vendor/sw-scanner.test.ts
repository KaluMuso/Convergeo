import { beforeAll, describe, expect, it } from "vitest";

import { isScanSyncApiUrl, isScannerPagePathname, SCANNER_PAGE_PATTERN } from "./sw-scanner";

const API_ORIGIN = "https://api.vergeo5.com";

beforeAll(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = API_ORIGIN;
  process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE = "production";
});

describe("sw-scanner predicates", () => {
  it("matches locale-prefixed event scan routes only", () => {
    expect(SCANNER_PAGE_PATTERN.test("/en/events/abc/scan")).toBe(true);
    expect(SCANNER_PAGE_PATTERN.test("/en/events/abc/scan/extra")).toBe(false);
    expect(isScannerPagePathname("/en/scan")).toBe(false);
  });

  it("recognises scan-sync on the configured API origin", () => {
    const ok = new URL("/events/e1/instances/i1/scan-sync", API_ORIGIN);
    const wrongHost = new URL("/events/e1/instances/i1/scan-sync", "https://other.test");
    expect(isScanSyncApiUrl(ok)).toBe(true);
    expect(isScanSyncApiUrl(wrongHost)).toBe(false);
  });
});
