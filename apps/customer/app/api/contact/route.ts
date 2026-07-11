import { checkRateLimit } from "../../[locale]/(marketing)/contact/_components/rate-limit";
import { validateContact } from "../../[locale]/(marketing)/contact/_components/validation";

import type { NextRequest } from "next/server";

export const runtime = "nodejs";

type ErrorCode = "invalid" | "rate_limited" | "bad_request" | "server_error";

function errorResponse(status: number, code: ErrorCode, details?: unknown): Response {
  return Response.json({ error: { code, message: code, details } }, { status });
}

function clientIp(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    return forwarded.split(",")[0]?.trim() || "unknown";
  }
  return request.headers.get("x-real-ip")?.trim() || "unknown";
}

/**
 * Contact → outbox handler. Owner-agnostic: this customer-app route validates and
 * rate-limits, then dispatches the message to support by email (Resend). There is no
 * public FastAPI contact endpoint to reuse, so this is the minimal owner-agnostic seam.
 * When Resend env is not configured (dev/preview), the message is logged and accepted.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const rate = checkRateLimit(`contact:${clientIp(request)}`);
  if (!rate.allowed) {
    return errorResponse(429, "rate_limited");
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return errorResponse(400, "bad_request");
  }

  if (typeof payload !== "object" || payload === null) {
    return errorResponse(400, "bad_request");
  }

  const result = validateContact(payload as Record<string, unknown>);
  if (!result.ok) {
    return errorResponse(422, "invalid", result.errors);
  }

  const { name, contact, message } = result.value;
  const apiKey = process.env.RESEND_API_KEY;
  const inbox = process.env.CONTACT_INBOX;
  const from = process.env.CONTACT_FROM ?? "Vergeo5 <noreply@vergeo5.com>";

  if (!apiKey || !inbox) {
    console.warn("[contact] Resend not configured — message accepted but not emailed.");
    return Response.json({ ok: true });
  }

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [inbox],
        reply_to: contact || undefined,
        subject: `Contact form: ${name}`,
        text: `From: ${name}\nContact: ${contact || "(not provided)"}\n\n${message}`,
      }),
    });

    if (!res.ok) {
      return errorResponse(502, "server_error");
    }
  } catch {
    return errorResponse(502, "server_error");
  }

  return Response.json({ ok: true });
}
