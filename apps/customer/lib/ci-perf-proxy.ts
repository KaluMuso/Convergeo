import { ciPerfServerEnabled, type CiPerfServerEnv } from "./ci-perf-harness";

const allowedQueries: Record<string, Record<string, RegExp>> = {
  cart: {},
  "products/smartphone-x1": {},
  "catalog/listings": {
    category_path: /^electronics$/,
    sort: /^(relevance|newest)$/,
    limit: /^([1-9]|1[0-9]|20)$/,
  },
};

export async function handleCiPerfProxy(
  request: Request,
  env: CiPerfServerEnv = process.env,
  transport: typeof fetch = fetch,
): Promise<Response> {
  const unavailable = () =>
    new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
  if (!ciPerfServerEnabled(env)) return unavailable();
  const url = new URL(request.url);
  if (url.origin !== env.NEXT_PUBLIC_SITE_URL) return unavailable();
  if (request.method !== "GET") return new Response(null, { status: 405 });
  const prefix = "/api/ci-perf/";
  if (!url.pathname.startsWith(prefix)) return unavailable();
  const path = url.pathname.slice(prefix.length);
  const queryRules = allowedQueries[path];
  if (!queryRules || !Object.hasOwn(allowedQueries, path) || /[%\\]/.test(url.pathname))
    return unavailable();
  for (const [key, value] of url.searchParams) {
    if (
      !Object.hasOwn(queryRules, key) ||
      !queryRules[key]?.test(value) ||
      url.searchParams.getAll(key).length !== 1
    )
      return unavailable();
  }
  const headers = new Headers({ Accept: "application/json" });
  const authorization = request.headers.get("authorization");
  if (path === "cart" && authorization?.startsWith("Bearer "))
    headers.set("Authorization", authorization);
  const guestCookie = request.headers
    .get("cookie")
    ?.split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => /^vergeo_guest_cart=[A-Za-z0-9_.-]+$/.test(cookie));
  if (path === "cart" && guestCookie) headers.set("Cookie", guestCookie);
  try {
    const upstream = await transport(`${env.CI_PERF_UPSTREAM_ORIGIN}/${path}${url.search}`, {
      method: "GET",
      headers,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    if (!(upstream.headers.get("content-type") ?? "").includes("application/json"))
      throw new Error("Invalid upstream content");
    const responseHeaders = new Headers({
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    const cookie = upstream.headers.get("set-cookie");
    if (
      path === "cart" &&
      cookie?.startsWith("vergeo_guest_cart=") &&
      !/;\s*domain=/i.test(cookie)
    ) {
      responseHeaders.set("Set-Cookie", cookie);
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}
