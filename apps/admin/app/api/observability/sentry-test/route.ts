import {
  isSentryTestEndpointEnabled,
  resolveEnvironment,
  resolveReleaseSha,
} from "@vergeo/observability";
import { timingSafeEqual } from "node:crypto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function secretsEqual(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

export async function POST(request: Request): Promise<Response> {
  if (!isSentryTestEndpointEnabled()) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  const expected = (process.env.SENTRY_TEST_SECRET || "").trim();
  const provided = request.headers.get("x-sentry-test-secret") || "";
  if (!expected || !secretsEqual(provided, expected)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) {
    return Response.json({ error: "sentry_dsn_unset" }, { status: 503 });
  }

  const Sentry = await import("@sentry/nextjs");
  const release = resolveReleaseSha();
  const environment = resolveEnvironment();

  const eventId = Sentry.captureMessage("Vergeo5 observability test event (admin)", {
    level: "error",
    tags: {
      application: "admin",
      test_event: "true",
      route: "/api/observability/sentry-test",
      ...(release ? { release_sha: release } : {}),
    },
  });
  await Sentry.flush(2000);

  return Response.json({
    ok: true,
    application: "admin",
    event_id: eventId,
    environment,
    release: release ?? null,
  });
}
