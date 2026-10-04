import assert from "node:assert/strict";
import test from "node:test";

import { configurePerfHarness, selectPerfAddress } from "./configure-perf-harness.mjs";

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
for (const [name, candidateRoutes, candidateInterfaces] of [
  ["no default", [], interfaces],
  ["ambiguous default", [...routes, ...routes], interfaces],
  ["missing interface", routes, interfaces.slice(1)],
  ["down interface", routes, [{ ...interfaces[0], flags: [] }]],
  ["loopback interface", routes, [{ ...interfaces[0], flags: ["UP", "LOOPBACK"] }]],
  [
    "multiple IPv4",
    routes,
    [{ ...interfaces[0], addr_info: [...interfaces[0].addr_info, ...interfaces[0].addr_info] }],
  ],
  ...["127.0.0.1", "8.8.8.8", "172.32.0.1", "10.2.3.256", "010.2.3.4"].map((ip) => [
    `invalid ${ip}`,
    routes,
    [{ ...interfaces[0], addr_info: [{ family: "inet", scope: "global", local: ip }] }],
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
