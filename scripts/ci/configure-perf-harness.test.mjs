import assert from "node:assert/strict";
import test from "node:test";

import {
  configurePerfHarness,
  perfHarnessEnvironmentLines,
  selectPerfAddress,
} from "./configure-perf-harness.mjs";

const routes = [{ dst: "default", dev: "eth0" }];
const interfaces = [
  {
    ifname: "eth0",
    flags: ["UP"],
    addr_info: [{ family: "inet", scope: "global", local: "10.2.3.4" }],
  },
  {
    ifname: "docker0",
    flags: ["UP"],
    addr_info: [{ family: "inet", scope: "global", local: "172.17.0.1" }],
  },
];
test("selects only the assigned IPv4 on the one active default interface", () => {
  assert.equal(selectPerfAddress(routes, interfaces), "10.2.3.4");
});
test("binds the public Supabase client to the same disposable stack as server data", () => {
  const lines = perfHarnessEnvironmentLines(
    {
      SUPABASE_URL: "http://127.0.0.1:54321",
      SUPABASE_ANON_KEY: "local-anon-key",
    },
    "10.2.3.4",
  );
  assert.ok(lines.includes("NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321"));
  assert.ok(lines.includes("NEXT_PUBLIC_SUPABASE_ANON_KEY=local-anon-key"));
  assert.ok(lines.includes("NEXT_PUBLIC_API_BASE_URL=http://10.2.3.4:8000"));
  assert.ok(lines.includes("CI_PERF_UPSTREAM_ORIGIN=http://10.2.3.4:8000"));
});
for (const [name, candidateRoutes, candidateInterfaces] of [
  ["no default", [], interfaces],
  ["ambiguous default", [...routes, ...routes], interfaces],
  ["missing interface", routes, interfaces.slice(1)],
  ["down interface", routes, [{ ...interfaces[0], flags: [] }]],
  ["loopback interface", routes, [{ ...interfaces[0], flags: ["UP", "LOOPBACK"] }]],
  [
    "multiple IPv4",
    routes,
    [
      {
        ...interfaces[0],
        addr_info: [...interfaces[0].addr_info, ...interfaces[0].addr_info],
      },
    ],
  ],
  ...["127.0.0.1", "8.8.8.8", "172.32.0.1", "10.2.3.256", "010.2.3.4"].map((ip) => [
    `invalid ${ip}`,
    routes,
    [
      {
        ...interfaces[0],
        addr_info: [{ family: "inet", scope: "global", local: ip }],
      },
    ],
  ]),
])
  test(`address selection closes: ${name}`, () =>
    assert.throws(() => selectPerfAddress(candidateRoutes, candidateInterfaces)));
test("ordinary or remote configuration fails before executing ip or touching GITHUB_ENV", () => {
  assert.throws(() => configurePerfHarness({}), /disposable/);
  assert.throws(
    () =>
      configurePerfHarness({
        CI: "true",
        GITHUB_ACTIONS: "true",
        GITHUB_ENV: "/denied",
        ENV: "development",
        SUPABASE_URL: "https://shared.example",
        SUPABASE_DB_URL: "postgresql://shared",
      }),
    /disposable/,
  );
});
