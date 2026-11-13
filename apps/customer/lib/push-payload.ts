/**
 * Web Push payload contract (flag `web_push`, default OFF) shared by the
 * customer service worker and mirrored in apps/vendor/public/push-sw.js:
 *
 *   { "title": string, "body": string, "url": "/en/account/orders/…", "badge": number }
 *
 * The API renders title/body in the recipient's locale before sending, so the
 * worker never needs i18n. `url` must be same-origin and path-only; anything
 * else falls back to the notifications page.
 */
export type PushDisplay = { title: string; body: string; url: string; badge: number | null };

const MAX_TEXT = 240;

function text(value: unknown): string {
  return typeof value === "string" ? value.slice(0, MAX_TEXT) : "";
}

export function safeNotificationUrl(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  if (!/^\/[A-Za-z0-9/_-]{0,240}$/.test(value) || value.startsWith("//")) return fallback;
  return value;
}

export function parsePushPayload(raw: string | null, fallbackUrl: string): PushDisplay {
  let data: Record<string, unknown> = {};
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object") data = parsed as Record<string, unknown>;
  } catch {
    data = {};
  }
  const badge =
    typeof data.badge === "number" && Number.isFinite(data.badge) && data.badge >= 0
      ? Math.floor(data.badge)
      : null;
  return {
    title: text(data.title) || "Convergeo",
    body: text(data.body),
    url: safeNotificationUrl(data.url, fallbackUrl),
    badge,
  };
}
