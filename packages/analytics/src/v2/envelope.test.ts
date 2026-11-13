import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  buildBatchV2,
  buildEventV2,
  ENVELOPE_VERSION,
  V2_EVENT_NAMES,
  V2_EVENT_VERSIONS,
} from "./envelope";

const here = dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(readFileSync(join(here, "../../registry/events.v2.json"), "utf8")) as {
  envelope_version: number;
  events: Record<string, { version: number }>;
};

const ctx = { id: "11111111-1111-4111-8111-111111111111", seq: 3, ts: 1000 };

describe("v2 registry parity", () => {
  it("TS event names and versions match the registry JSON", () => {
    expect(registry.envelope_version).toBe(ENVELOPE_VERSION);
    expect([...V2_EVENT_NAMES].sort()).toEqual(Object.keys(registry.events).sort());
    for (const name of V2_EVENT_NAMES) {
      expect(V2_EVENT_VERSIONS[name]).toBe(registry.events[name]!.version);
    }
  });
});

describe("buildEventV2", () => {
  it("keeps the v1 fields and adds id/ev/seq/page", () => {
    const wire = buildEventV2("product_view", { product_id: "p" }, { ...ctx, page: "pdp" });
    expect(wire).toEqual({
      event: "product_view",
      props: { product_id: "p" },
      ts: 1000,
      id: ctx.id,
      ev: 1,
      seq: 3,
      page: "pdp",
    });
  });

  it("omits page when absent and defaults unknown versions to 1", () => {
    const wire = buildEventV2("cart_add", {}, ctx);
    expect(wire.ev).toBe(1);
    expect("page" in wire).toBe(false);
  });
});

describe("buildBatchV2", () => {
  const identity = {
    app: "customer" as const,
    legacySessionId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    anonId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    sessionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    countsOnly: false,
  };

  it("is a superset of the v1 body (session_id + events)", () => {
    const batch = buildBatchV2([buildEventV2("page_view", {}, ctx)], identity);
    expect(batch.v).toBe(2);
    expect(batch.session_id).toBe(identity.legacySessionId);
    expect(batch.anon).toBe(identity.anonId);
    expect(batch.sid).toBe(identity.sessionId);
    expect(batch.events[0]!.event).toBe("page_view");
  });

  it("attaches no identifiers in counts-only mode", () => {
    const batch = buildBatchV2([], { ...identity, countsOnly: true });
    expect(batch).toEqual({ v: 2, app: "customer", events: [], consent: "denied" });
  });
});
