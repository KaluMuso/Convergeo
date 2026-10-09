import type { SendSmsHookPayload } from "./hook.ts";

export type WahaResult = { ok: true } | { ok: false; status: 400 | 500 | 503 };

const MAX_HOOK_MS = 5_000;
const HANDOFF_MS = 4_000;
const FETCH_MS = 2_800;
const STAGING_SUPABASE_URL = "https://iyasmrmbcrvlfxpzescb.supabase.co";
const STAGING_N8N_OTP_URL = "https://n8n.staging.vergeo5.com/webhook/convergeo-auth-otp-draft";

export function selectOtpTransport(
  env: Record<string, string | undefined>,
): "at" | "waha" | "disabled" | "invalid" {
  const staging = env.SUPABASE_URL === STAGING_SUPABASE_URL;
  const selected = env.SMS_OTP_TRANSPORT || (staging ? "disabled" : "at");
  if (selected === "at") return !staging || env.AT_ENVIRONMENT === "sandbox" ? "at" : "disabled";
  if (selected === "waha") return staging && env.WAHA_OTP_ENABLED === "true" ? "waha" : "disabled";
  if (selected === "disabled") return "disabled";
  return "invalid";
}

function validUrl(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    if (url.href !== STAGING_N8N_OTP_URL) return undefined;
    return STAGING_N8N_OTP_URL;
  } catch {
    return undefined;
  }
}

export function validateWahaPayload(
  value: SendSmsHookPayload,
): { phone: string; otp: string } | undefined {
  const phone = value?.user?.phone;
  const otp = value?.sms?.otp;
  if (typeof phone !== "string" || typeof otp !== "string") return undefined;
  // Supabase can store the phone without '+'. Never accept whitespace, chat IDs, or group IDs.
  const normalized = phone.startsWith("+") ? phone : `+${phone}`;
  if (!/^\+[1-9][0-9]{7,14}$/.test(normalized) || !/^[0-9]{4,8}$/.test(otp)) return undefined;
  return { phone: normalized, otp };
}

function requestIdFromHeaders(headers: Headers): string | undefined {
  const requestId = headers.get("webhook-id");
  return requestId && /^[A-Za-z0-9_-]{8,64}$/.test(requestId) ? requestId : undefined;
}

function timestampFromHeaders(headers: Headers, now: number): number | undefined {
  const raw = headers.get("webhook-timestamp");
  if (!raw || !/^[0-9]{10}$/.test(raw)) return undefined;
  const ms = Number(raw) * 1000;
  return ms <= now + 5_000 && ms >= now - 30_000 ? ms : undefined;
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function sendWahaOtp(
  payload: SendSmsHookPayload,
  sourceHeaders: Headers,
  env: Record<string, string | undefined>,
  fetchImpl: typeof fetch = fetch,
  now = Date.now(),
): Promise<WahaResult> {
  const validated = validateWahaPayload(payload);
  if (!validated) return { ok: false, status: 400 };

  const requestId = requestIdFromHeaders(sourceHeaders);
  const timestamp = timestampFromHeaders(sourceHeaders, now);
  if (!requestId || timestamp === undefined) return { ok: false, status: 400 };

  const url = validUrl(env.WAHA_OTP_N8N_WEBHOOK_URL);
  const authToken = env.WAHA_OTP_N8N_AUTH_TOKEN;
  const hmacSecret = env.WAHA_OTP_N8N_HMAC_SECRET;
  if (!url || !authToken || authToken.length < 32 || !hmacSecret || hmacSecret.length < 32) {
    return { ok: false, status: 500 };
  }

  const deadline = Math.min(now + HANDOFF_MS, timestamp + MAX_HOOK_MS);
  if (deadline <= now + FETCH_MS) return { ok: false, status: 400 };
  let signature: string;
  try {
    const signingInput = `v1\n${Math.floor(timestamp / 1000)}\n${requestId}\n${deadline}\n${validated.phone}\n${validated.otp}`;
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(hmacSecret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    signature = hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(signingInput)));
  } catch {
    return { ok: false, status: 500 };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_MS);
  try {
    const response = await fetchImpl(url, {
      method: "POST",
      redirect: "error",
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "X-Convergeo-OTP-Auth": authToken,
        "X-Convergeo-OTP-Signature": signature,
      },
      body: JSON.stringify({
        version: 1,
        requestId,
        timestamp: Math.floor(timestamp / 1000),
        deadline,
        phone: validated.phone,
        otp: validated.otp,
      }),
    });
    if (response.status !== 200) return { ok: false, status: 503 };
    const body = await response.text();
    if (body.length > 512) return { ok: false, status: 503 };
    const receipt = JSON.parse(body);
    if (
      receipt?.accepted === true &&
      receipt?.requestId === requestId &&
      Object.keys(receipt).length === 2
    )
      return { ok: true };
    return { ok: false, status: 503 };
  } catch {
    // A timeout or broken connection has an uncertain send outcome. Never retry here.
    return { ok: false, status: 503 };
  } finally {
    clearTimeout(timer);
  }
}
