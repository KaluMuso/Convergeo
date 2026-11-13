import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import process from "node:process";
import { pathToFileURL } from "node:url";

export function selectPerfAddress(routes, interfaces) {
  if (routes.length !== 1 || routes[0].dst !== "default" || !routes[0].dev)
    throw new Error("Ambiguous default interface");
  const device = routes[0].dev;
  const matching = interfaces.filter(
    (entry) =>
      entry.ifname === device && entry.flags.includes("UP") && !entry.flags.includes("LOOPBACK"),
  );
  if (matching.length !== 1) throw new Error("Default interface unavailable");
  const addresses = matching[0].addr_info.filter(
    (entry) => entry.family === "inet" && entry.scope === "global",
  );
  if (addresses.length !== 1) throw new Error("Ambiguous default-interface IPv4 address");
  const ip = addresses[0].local;
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip ?? "");
  if (!match) throw new Error("Invalid assigned IPv4 address");
  const parts = match.slice(1).map(Number);
  if (
    parts.some((part, index) => part > 255 || String(part) !== match[index + 1]) ||
    !(
      parts[0] === 10 ||
      (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
      (parts[0] === 192 && parts[1] === 168)
    )
  ) {
    throw new Error("Default interface requires RFC1918 IPv4");
  }
  return ip;
}

export function perfHarnessEnvironmentLines(env, address) {
  return [
    "CI_PERF_HARNESS=1",
    "NEXT_PUBLIC_CI_PERF_HARNESS=1",
    "NEXT_PUBLIC_DEPLOYMENT_PLANE=preview",
    // Server-rendered categories use the public Supabase client. Point both
    // server and browser at the disposable seeded stack, not example.supabase.co.
    `NEXT_PUBLIC_SUPABASE_URL=${env.SUPABASE_URL}`,
    `NEXT_PUBLIC_SUPABASE_ANON_KEY=${env.SUPABASE_ANON_KEY}`,
    `NEXT_PUBLIC_API_BASE_URL=http://${address}:8000`,
    `CI_PERF_UPSTREAM_ORIGIN=http://${address}:8000`,
    "NEXT_PUBLIC_SITE_URL=http://localhost:3000",
    "",
  ];
}

export function configurePerfHarness(env = process.env) {
  if (
    env.CI !== "true" ||
    env.GITHUB_ACTIONS !== "true" ||
    !env.GITHUB_ENV ||
    env.VERCEL ||
    env.VERCEL_ENV ||
    env.ENV !== "development" ||
    env.SUPABASE_URL !== "http://127.0.0.1:54321" ||
    !env.SUPABASE_ANON_KEY ||
    env.SUPABASE_DB_URL !== "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
  ) {
    throw new Error("Performance configuration requires the disposable GitHub CI stack");
  }
  const routes = JSON.parse(
    execFileSync("ip", ["-j", "route", "show", "default"], {
      encoding: "utf8",
    }),
  );
  const interfaces = JSON.parse(execFileSync("ip", ["-j", "addr", "show"], { encoding: "utf8" }));
  const address = selectPerfAddress(routes, interfaces);
  appendFileSync(env.GITHUB_ENV, perfHarnessEnvironmentLines(env, address).join("\n"));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  configurePerfHarness();
