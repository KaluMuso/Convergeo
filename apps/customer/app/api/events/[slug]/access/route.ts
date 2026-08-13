import { NextResponse, type NextRequest } from "next/server";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";
import { eventAccessCookieName } from "../../../../../lib/event-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type UnlockResponse = {
  access_proof?: unknown;
  expires_at?: unknown;
};

function unavailable(): NextResponse {
  // Do not reveal whether a private slug exists or whether a supplied code was
  // close. The FastAPI endpoint follows the same fail-closed contract.
  return NextResponse.json(
    { error: { code: "event_access_unavailable", message: "This event is unavailable." } },
    { status: 403 },
  );
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> },
): Promise<NextResponse> {
  const { slug } = await context.params;
  let body: { code?: unknown };
  try {
    body = (await request.json()) as { code?: unknown };
  } catch {
    return unavailable();
  }

  const code = typeof body.code === "string" ? body.code.trim() : "";
  if (!code || code.length > 128) {
    return unavailable();
  }

  const url = absoluteApiUrl(`/events/${encodeURIComponent(slug)}/access/unlock`);
  if (!url) {
    return unavailable();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ code }),
    });
  } catch {
    return unavailable();
  }

  if (!upstream.ok) {
    return unavailable();
  }

  const payload = (await upstream.json()) as UnlockResponse;
  if (typeof payload.access_proof !== "string" || typeof payload.expires_at !== "string") {
    return unavailable();
  }

  const response = NextResponse.json({ ok: true, expires_at: payload.expires_at });
  response.cookies.set(eventAccessCookieName(slug), payload.access_proof, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 15 * 60,
    path: "/",
  });
  return response;
}
