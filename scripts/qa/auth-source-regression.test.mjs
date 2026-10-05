// Dependency-free source checks for auth routing and role claims. Run with
// `node --experimental-strip-types --test scripts/qa/auth-source-regression.test.mjs`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { sanitizeNextPath } from "../../packages/auth/src/safe-next.ts";
import { getRolesFromClaims } from "../../packages/auth/src/roles.ts";
import { isPasswordLengthAllowed } from "../../apps/customer/app/[locale]/(auth)/_components/email-password-policy.ts";

test("existing passwords reach Auth while new passwords keep the UI minimum", () => {
  assert.equal(isPasswordLengthAllowed("pass123", "login"), true);
  assert.equal(isPasswordLengthAllowed("pass123", "signup"), false);
  assert.equal(isPasswordLengthAllowed("password1", "signup"), true);
});

test("login return stays on the requested locale and origin", () => {
  assert.equal(sanitizeNextPath("en", "/en/account/orders", "/en"), "/en/account/orders");
  for (const unsafe of [
    "https://other.example.test/",
    "//other.example.test/",
    "%2F%2Fother.example.test/",
    "/fr/account/orders",
    "/en/../admin",
    "/en\\other.example.test",
  ]) {
    assert.equal(sanitizeNextPath("en", unsafe, "/en"), "/en", unsafe);
  }
});

test("portal role fast path uses app_metadata claims only", () => {
  assert.deepEqual(
    getRolesFromClaims({ app_metadata: { roles: ["vendor", "admin", "invalid"] } }),
    ["vendor", "admin"],
  );
  assert.deepEqual(getRolesFromClaims({ user_metadata: { roles: ["admin"] } }), []);
  assert.deepEqual(getRolesFromClaims({ app_metadata: { roles: "admin" } }), []);
});
