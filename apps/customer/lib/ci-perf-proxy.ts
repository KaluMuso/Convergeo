import { ciPerfServerEnabled, type CiPerfServerEnv } from "./ci-perf-harness";
import { CI_PERF_POST_PATHS, readCiPerfPostBody } from "./ci-perf-post-body";

const allowedQueries: Record<string, Record<string, RegExp>> = {
  cart: {},
  "products/smartphone-x1": {},
  "catalog/listings": {
    category_path: /^electronics$/,
    sort: /^(relevance|newest)$/,
    limit: /^([1-9]|1[0-9]|20)$/,
  },
  "cart/revalidate": {},
  "telemetry/views": {},
  "telemetry/frontend-errors": {},
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
  const post = CI_PERF_POST_PATHS.includes(path);
  if (request.method !== (post ? "POST" : "GET"))
    return new Response(null, { status: 405, headers: { "Cache-Control": "no-store" } });
  let body: string | undefined;
  if (post) {
    const validated = await readCiPerfPostBody(path, request, env.NEXT_PUBLIC_SITE_URL!);
    if ("status" in validated)
      return new Response(null, {
        status: validated.status,
        headers: { "Cache-Control": "no-store" },
      });
    body = validated.body;
  }
  const headers = new Headers({ Accept: "application/json" });
  if (post && path !== "cart/revalidate") headers.set("Content-Type", "application/json");
  const cart = path === "cart" || path === "cart/revalidate";
  const authorization = request.headers.get("authorization");
  if (cart && authorization?.startsWith("Bearer ")) headers.set("Authorization", authorization);
  const guestCookie = request.headers
    .get("cookie")
    ?.split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => /^vergeo_guest_cart=[A-Za-z0-9_.-]+$/.test(cookie));
  if (cart && guestCookie) headers.set("Cookie", guestCookie);
  try {
    const upstream = await transport(`${env.CI_PERF_UPSTREAM_ORIGIN}/${path}${url.search}`, {
      method: request.method,
      ...(post ? { body } : {}),
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
    if (cart && cookie?.startsWith("vergeo_guest_cart=") && !/;\s*domain=/i.test(cookie)) {
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
