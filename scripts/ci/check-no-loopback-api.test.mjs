import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { previewTargetsProductionApi } from "./check-no-loopback-api.mjs";

describe("previewTargetsProductionApi", () => {
  it("fails closed when a Preview build points at the production API", () => {
    assert.equal(
      previewTargetsProductionApi({
        VERCEL_ENV: "preview",
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
      }),
      true,
    );
    assert.equal(
      previewTargetsProductionApi({
        VERCEL_ENV: "preview",
        NEXT_PUBLIC_VERGEO_API_URL: "https://api.vergeo5.com/",
      }),
      true,
    );
  });

  it("allows staging API on Preview and production API on Production", () => {
    assert.equal(
      previewTargetsProductionApi({
        VERCEL_ENV: "preview",
        NEXT_PUBLIC_API_BASE_URL: "https://api.staging.vergeo5.com",
      }),
      false,
    );
    assert.equal(
      previewTargetsProductionApi({
        VERCEL_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.vergeo5.com",
      }),
      false,
    );
  });
});
