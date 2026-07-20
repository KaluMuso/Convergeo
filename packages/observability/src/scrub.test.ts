import { describe, expect, it } from "vitest";

import {
  EMAIL_MASK,
  PHONE_MASK,
  REDACTED,
  TOKEN_MASK,
  isSentryTestEndpointEnabled,
  resolveEnvironment,
  resolveReleaseSha,
  scrub,
} from "./scrub";

const PHONE = "+260977123456";
const LOCAL_PHONE = "0977123456";
const EMAIL = "buyer@example.com";
const BEARER = "Bearer sk_live_supersecrettoken0099";
const JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc-123_XYZ";

describe("scrub", () => {
  it("redacts sensitive keys including cookies, payments, and signatures", () => {
    const scrubbed = scrub({
      cookie: "session=abc",
      refresh_token: "rt_1",
      access_token: BEARER,
      service_role_key: "srk",
      "x-lenco-signature": "deadbeef",
      webhook_signature: "sig",
      payment_payload: { amount: 100 },
      card_number: "4622943127013705",
      cvv: "838",
      quantity: 3,
      order_id: "ord-safe-1",
    }) as Record<string, unknown>;

    expect(scrubbed.cookie).toBe(REDACTED);
    expect(scrubbed.refresh_token).toBe(REDACTED);
    expect(scrubbed.access_token).toBe(REDACTED);
    expect(scrubbed.service_role_key).toBe(REDACTED);
    expect(scrubbed["x-lenco-signature"]).toBe(REDACTED);
    expect(scrubbed.webhook_signature).toBe(REDACTED);
    expect(scrubbed.payment_payload).toBe(REDACTED);
    expect(scrubbed.card_number).toBe(REDACTED);
    expect(scrubbed.cvv).toBe(REDACTED);
    expect(scrubbed.quantity).toBe(3);
    expect(scrubbed.order_id).toBe("ord-safe-1");
  });

  it("masks free-text phone, email, and tokens", () => {
    const msg = scrub(
      `login failed for ${EMAIL} from ${PHONE} using ${BEARER} and jwt ${JWT} local ${LOCAL_PHONE}`,
    ) as string;
    expect(msg).toContain(EMAIL_MASK);
    expect(msg).toContain(PHONE_MASK);
    expect(msg).toContain(TOKEN_MASK);
    expect(msg).not.toContain(EMAIL);
    expect(msg).not.toContain(PHONE);
    expect(msg).not.toContain(LOCAL_PHONE);
    expect(msg).not.toContain("supersecrettoken");
  });
});

describe("environment helpers", () => {
  it("resolves release SHA from immutable commit env vars", () => {
    expect(resolveReleaseSha({ GIT_SHA: "abc123" })).toBe("abc123");
    expect(resolveReleaseSha({ VERCEL_GIT_COMMIT_SHA: "def456" })).toBe("def456");
    expect(resolveReleaseSha({ NEXT_PUBLIC_SENTRY_RELEASE: "rel789" })).toBe("rel789");
    expect(resolveReleaseSha({})).toBeUndefined();
  });

  it("resolves environment labels with fallbacks", () => {
    expect(resolveEnvironment({ NEXT_PUBLIC_SENTRY_ENVIRONMENT: "staging" })).toBe("staging");
    expect(resolveEnvironment({ VERCEL_ENV: "preview" })).toBe("preview");
    expect(resolveEnvironment({})).toBe("development");
  });

  it("disables sentry-test in production without explicit enable flag", () => {
    expect(
      isSentryTestEndpointEnabled({
        NODE_ENV: "production",
        SENTRY_TEST_SECRET: "secret",
      }),
    ).toBe(false);
    expect(
      isSentryTestEndpointEnabled({
        NODE_ENV: "production",
        SENTRY_TEST_SECRET: "secret",
        ENABLE_SENTRY_TEST_ENDPOINT: "true",
      }),
    ).toBe(true);
    expect(
      isSentryTestEndpointEnabled({
        NODE_ENV: "development",
        SENTRY_TEST_SECRET: "secret",
      }),
    ).toBe(true);
    expect(isSentryTestEndpointEnabled({ NODE_ENV: "development" })).toBe(false);
  });
});
