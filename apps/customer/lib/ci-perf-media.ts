import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ciPerfServerEnabled, type CiPerfServerEnv } from "./ci-perf-harness";

export async function handleCiPerfMedia(
  request: Request,
  env: CiPerfServerEnv = process.env,
  read: typeof readFile = readFile,
): Promise<Response> {
  const unavailable = () =>
    new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
  if (!ciPerfServerEnabled(env)) return unavailable();
  const url = new URL(request.url);
  if (url.origin !== env.NEXT_PUBLIC_SITE_URL) return unavailable();
  if (request.method !== "GET") return new Response(null, { status: 405 });
  if (
    url.pathname !== "/api/ci-perf-media" ||
    [...url.searchParams.keys()].some((key) => key !== "width")
  )
    return unavailable();
  const width = url.searchParams.get("width");
  if (
    url.searchParams.getAll("width").length !== 1 ||
    !/^(24|360|720|1080|1200)$/.test(width ?? "")
  )
    return unavailable();
  try {
    const image = await read(join(process.cwd(), "ci-fixtures", `smartphone-x1-${width}.webp`));
    return new Response(new Uint8Array(image), {
      headers: { "Content-Type": "image/webp", "Cache-Control": "no-store" },
    });
  } catch {
    return unavailable();
  }
}
