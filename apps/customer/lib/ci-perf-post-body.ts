/** Bounded payloads for three existing disposable-CI endpoints. */
const PHONE = "b1000000-0000-0000-0000-000000000001";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BYTES = 16_384;

export const CI_PERF_POST_PATHS = Object.freeze([
  "cart/revalidate",
  "telemetry/views",
  "telemetry/frontend-errors",
]);

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function views(value: Record<string, unknown>): boolean {
  if (Object.keys(value).some((key) => !["session_id", "listing_id", "listing_ids"].includes(key)))
    return false;
  if (typeof value.session_id !== "string" || !UUID.test(value.session_id)) return false;
  const single = Object.hasOwn(value, "listing_id");
  const batch = Object.hasOwn(value, "listing_ids");
  if (single === batch) return false;
  return single
    ? value.listing_id === PHONE
    : Array.isArray(value.listing_ids) &&
        value.listing_ids.length === 1 &&
        value.listing_ids[0] === PHONE;
}

function frontendError(value: Record<string, unknown>, site: string): boolean {
  const limits: Record<string, number> = {
    message: 500,
    digest: 128,
    stack: 8_000,
    locale: 8,
    url: 2_000,
    userAgent: 500,
    user_agent: 500,
  };
  if (
    typeof value.message !== "string" ||
    !value.message.length ||
    value.application !== "customer" ||
    typeof value.boundary !== "string" ||
    !["route", "global"].includes(value.boundary)
  )
    return false;
  for (const [key, field] of Object.entries(value)) {
    if (["application", "boundary"].includes(key)) continue;
    if (!Object.hasOwn(limits, key) || typeof field !== "string" || field.length > limits[key]!)
      return false;
  }
  if (value.locale !== undefined && value.locale !== "en") return false;
  if (value.url !== undefined) {
    try {
      const url = new URL(String(value.url));
      if (
        url.origin !== site ||
        !["/en", "/en/c/electronics", "/en/p/smartphone-x1", "/en/search", "/en/checkout"].includes(
          url.pathname,
        )
      )
        return false;
    } catch {
      return false;
    }
  }
  return true;
}

export async function readCiPerfPostBody(
  path: string,
  request: Request,
  site: string,
): Promise<{ body: string } | { status: number }> {
  if (!CI_PERF_POST_PATHS.includes(path) || request.headers.get("origin") !== site)
    return { status: 403 };
  const advertised = request.headers.get("content-length");
  if (advertised !== null && (!/^\d+$/.test(advertised) || Number(advertised) > MAX_BYTES))
    return { status: 413 };
  let body = "";
  let size = 0;
  const reader = request.body?.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  try {
    if (reader) {
      for (;;) {
        const part = await reader.read();
        if (part.done) break;
        size += part.value.byteLength;
        if (size > MAX_BYTES) {
          await reader.cancel();
          return { status: 413 };
        }
        body += decoder.decode(part.value, { stream: true });
      }
      body += decoder.decode();
    }
    if (path === "cart/revalidate") return size === 0 ? { body } : { status: 400 };
    if (
      request.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() !==
      "application/json"
    )
      return { status: 415 };
    const value: unknown = JSON.parse(body);
    if (!record(value)) return { status: 400 };
    if (path === "telemetry/views" ? !views(value) : !frontendError(value, site))
      return { status: 400 };
    return { body: JSON.stringify(value) };
  } catch {
    return { status: 400 };
  } finally {
    reader?.releaseLock();
  }
}
