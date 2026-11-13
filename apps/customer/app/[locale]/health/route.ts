import { isE2EMockSessionAllowed } from "@vergeo/config/api-base-url";

import { resolveApiHost } from "../../../lib/api-base-url";

function buildId(): string {
  return (
    process.env.NEXT_PUBLIC_VERGEO_BUILD_ID ||
    process.env.VERCEL_GIT_COMMIT_SHA ||
    process.env.GIT_SHA ||
    "unknown"
  );
}

export function GET() {
  return Response.json({
    status: "ok",
    app: "customer",
    env: process.env.NEXT_PUBLIC_VERGEO_ENV || process.env.VERCEL_ENV || "unknown",
    buildId: buildId(),
    // Same effective configuration the app itself fetches with (host-only —
    // never the full URL, never a secret). null when unset/malformed:
    // never silently substitutes a default host.
    apiHost: resolveApiHost(process.env),
    // Boolean only — never the injected session/access-token itself. Lets the
    // E2E preflight prove the staging Preview build actually compiled the
    // payment-mock session contract in BEFORE any browser test runs, instead
    // of every mock-session-dependent spec silently timing out. Always false
    // on Production (see isE2EMockSessionAllowed's fail-closed contract).
    e2eMockSessionEnabled: isE2EMockSessionAllowed(process.env),
  });
}
