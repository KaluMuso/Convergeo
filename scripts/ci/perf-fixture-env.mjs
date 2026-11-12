import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

function ipv4(value) {
  if (!/^(0|[1-9]\d{0,2})(\.(0|[1-9]\d{0,2})){3}$/.test(value ?? "")) {
    throw new Error("Expected an unambiguous IPv4 address");
  }
  const octets = value.split(".").map(Number);
  if (octets.some((part) => part > 255)) throw new Error("Invalid IPv4 address");
  return octets;
}

function privateAddress(value) {
  const [a, b] = ipv4(value);
  if (!(a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168))) {
    throw new Error("Fixture transport requires an RFC1918 Docker bridge address");
  }
  return value;
}

/** Only the existing default Docker bridge, never a DNS alias or public NIC. */
export function bridgeEnvironment(networks, interfaces) {
  if (!Array.isArray(networks) || networks.length !== 1) throw new Error("Ambiguous bridge");
  const network = networks[0];
  if (
    network.Name !== "bridge" ||
    network.Driver !== "bridge" ||
    network.Options?.["com.docker.network.bridge.name"] !== "docker0" ||
    network.Options?.["com.docker.network.bridge.default_bridge"] !== "true" ||
    network.IPAM?.Config?.length !== 1
  ) {
    throw new Error("Expected the existing default docker0 bridge");
  }
  const { Gateway: gateway, Subnet: subnet } = network.IPAM.Config[0];
  privateAddress(gateway);
  const [address, prefixText, ...extra] = String(subnet).split("/");
  const prefix = Number(prefixText);
  if (extra.length || !/^\d+$/.test(prefixText ?? "") || prefix < 8 || prefix > 30) {
    throw new Error("Invalid bridge subnet");
  }
  privateAddress(address);
  const asNumber = (value) => ipv4(value).reduce((n, part) => n * 256 + part, 0);
  const block = 2 ** (32 - prefix);
  const start = asNumber(address);
  const host = asNumber(gateway);
  if (start % block !== 0 || host <= start || host >= start + block - 1) {
    throw new Error("Gateway is not a host in the declared bridge subnet");
  }
  if (!Array.isArray(interfaces) || interfaces.length !== 1 || interfaces[0].ifname !== "docker0") {
    throw new Error("Expected exactly the docker0 interface");
  }
  const addresses = interfaces[0].addr_info?.filter((row) => row.family === "inet") ?? [];
  if (
    addresses.length !== 1 ||
    addresses[0].local !== gateway ||
    addresses[0].prefixlen !== prefix
  ) {
    throw new Error("Docker gateway does not match the actual docker0 address");
  }
  return {
    PERF_FIXTURE_API_HOST: gateway,
    NEXT_PUBLIC_API_BASE_URL: `https://${gateway}:8000`,
    NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
  };
}

/** Export only the disposable public client URL and anon key, never privileged values. */
export function publicSupabaseEnvironment(origin, anonKey) {
  const url = new URL(origin);
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(url.hostname) ||
    url.port !== "54321" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error("Expected the runner-local Supabase public origin");
  }
  const parts = String(anonKey).split(".");
  if (parts.length !== 3 || parts.some((part) => !/^[A-Za-z0-9_-]+$/.test(part))) {
    throw new Error("Expected the pinned local stack's anon JWT");
  }
  let payload;
  try {
    payload = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
  } catch {
    throw new Error("Invalid local anon JWT payload");
  }
  if (payload.role !== "anon") throw new Error("Only the local anon role may be public");
  return {
    NEXT_PUBLIC_SUPABASE_URL: url.origin,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: anonKey,
  };
}

function main() {
  if (process.env.GITHUB_ACTIONS !== "true" || !process.env.GITHUB_ENV) {
    throw new Error("This fixture setup is only for the existing disposable Actions runner");
  }
  let output;
  if (process.argv[2] === "--public-supabase") {
    output = publicSupabaseEnvironment(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);
  } else if (process.argv[2] === "--api-bridge") {
    output = bridgeEnvironment(
      JSON.parse(execFileSync("docker", ["network", "inspect", "bridge"], { encoding: "utf8" })),
      JSON.parse(execFileSync("ip", ["-j", "-4", "addr", "show", "docker0"], { encoding: "utf8" })),
    );
  } else {
    throw new Error("Choose an explicit fixture setup operation");
  }
  appendFileSync(
    process.env.GITHUB_ENV,
    Object.entries(output)
      .map(([key, value]) => `${key}=${value}\n`)
      .join(""),
  );
  console.log("Configured verified disposable fixture inputs (public client values only)");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
