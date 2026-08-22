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
    app: "admin",
    env: process.env.NEXT_PUBLIC_VERGEO_ENV || process.env.VERCEL_ENV || "unknown",
    buildId: buildId(),
    // Same effective configuration the app itself fetches with (host-only —
    // never the full URL, never a secret, never session/user/admin data).
    // null when unset/malformed: never silently substitutes a default host.
    apiHost: resolveApiHost(process.env),
  });
}
