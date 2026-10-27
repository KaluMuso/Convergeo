import assert from "node:assert/strict";
import { test } from "node:test";

import { bridgeEnvironment, publicSupabaseEnvironment } from "./perf-fixture-env.mjs";

const network = () => [
  {
    Name: "bridge",
    Driver: "bridge",
    Options: {
      "com.docker.network.bridge.name": "docker0",
      "com.docker.network.bridge.default_bridge": "true",
    },
    IPAM: { Config: [{ Gateway: "172.17.0.1", Subnet: "172.17.0.0/16" }] },
  },
];
const nic = () => [
  { ifname: "docker0", addr_info: [{ family: "inet", local: "172.17.0.1", prefixlen: 16 }] },
];

test("uses only the matched existing bridge, with preview origin guards unchanged", () => {
  assert.deepEqual(bridgeEnvironment(network(), nic()), {
    PERF_FIXTURE_API_HOST: "172.17.0.1",
    NEXT_PUBLIC_API_BASE_URL: "http://172.17.0.1:8000",
    NEXT_PUBLIC_DEPLOYMENT_PLANE: "preview",
  });
});

for (const host of [
  "127.0.0.1",
  "0.0.0.0",
  "8.8.8.8",
  "169.254.1.1",
  "api.staging.vergeo5.com",
  "api",
  "172.017.0.1",
]) {
  test(`rejects unsupported gateway ${host}`, () => {
    const n = network();
    n[0].IPAM.Config[0].Gateway = host;
    assert.throws(() => bridgeEnvironment(n, nic()));
  });
}
for (const [label, modify] of [
  [
    "public NIC",
    (n, i) => {
      i[0].ifname = "eth0";
    },
  ],
  [
    "unmatched address",
    (n, i) => {
      i[0].addr_info[0].local = "172.17.0.2";
    },
  ],
  [
    "ambiguous address",
    (n, i) => {
      i[0].addr_info.push({ ...i[0].addr_info[0] });
    },
  ],
  [
    "nondefault network",
    (n) => {
      n[0].Options["com.docker.network.bridge.default_bridge"] = "false";
    },
  ],
  [
    "different bridge",
    (n) => {
      n[0].Options["com.docker.network.bridge.name"] = "br-other";
    },
  ],
  [
    "different driver",
    (n) => {
      n[0].Driver = "host";
    },
  ],
  [
    "multiple networks",
    (n) => {
      n.push(n[0]);
    },
  ],
  [
    "multiple subnets",
    (n) => {
      n[0].IPAM.Config.push(n[0].IPAM.Config[0]);
    },
  ],
  [
    "out-of-subnet",
    (n) => {
      n[0].IPAM.Config[0].Subnet = "10.0.0.0/24";
    },
  ],
  [
    "broadcast",
    (n) => {
      n[0].IPAM.Config[0].Gateway = "172.17.255.255";
    },
  ],
  [
    "bad prefix",
    (n) => {
      n[0].IPAM.Config[0].Subnet = "172.17.0.0/0";
    },
  ],
]) {
  test(`rejects ${label}`, () => {
    const n = network();
    const i = nic();
    modify(n, i);
    assert.throws(() => bridgeEnvironment(n, i));
  });
}

const jwt = (role) =>
  ["header", Buffer.from(JSON.stringify({ role })).toString("base64url"), "signature"].join(".");
test("publishes exactly the local public-client fields", () => {
  assert.deepEqual(publicSupabaseEnvironment("http://127.0.0.1:54321", jwt("anon")), {
    NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: jwt("anon"),
  });
});
for (const origin of [
  "https://example.supabase.co",
  "https://dpadrlxukcjbewpqympu.supabase.co",
  "http://127.0.0.1:8000",
  "http://localhost:54321/rest/v1",
  "http://user:password@localhost:54321",
]) {
  test(`rejects nonfixture Supabase origin ${origin}`, () =>
    assert.throws(() => publicSupabaseEnvironment(origin, jwt("anon"))));
}
for (const key of [jwt("service_role"), jwt("authenticated"), "not-a-jwt", "a.e30.b"]) {
  test("rejects privileged or invalid public keys without exposing them", () =>
    assert.throws(() => publicSupabaseEnvironment("http://127.0.0.1:54321", key)));
}
