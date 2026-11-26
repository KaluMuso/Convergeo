import { describe, expect, it } from "vitest";

import {
  buildAuditQuery,
  diffRows,
  entityKey,
  formatDiffValue,
  type AuditEntry,
  type AuditFilters,
} from "./audit-log-board";

const EMPTY: AuditFilters = {
  actor: "",
  action: "",
  entityType: "",
  entityId: "",
  outcome: "",
  from: "",
  to: "",
};

describe("audit log query builder", () => {
  it("sends only the filters that were set, with a bounded page", () => {
    expect(buildAuditQuery(EMPTY, null)).toEqual({ query: "limit=50" });
    const built = buildAuditQuery(
      {
        ...EMPTY,
        actor: "00000000-0000-0000-0000-0000000000a1",
        action: "admin.orders.",
        outcome: "denied",
        from: "2026-11-01",
        to: "2026-11-13",
      },
      { before: "2026-11-12T10:00:00.000Z", beforeId: "00000000-0000-0000-0000-0000000000b2" },
    );
    expect("query" in built && new URLSearchParams(built.query).get("action")).toBe(
      "admin.orders.",
    );
    expect("query" in built && new URLSearchParams(built.query).get("outcome")).toBe("denied");
    expect("query" in built && new URLSearchParams(built.query).get("from")).toBe(
      "2026-11-01T00:00:00.000Z",
    );
    expect("query" in built && new URLSearchParams(built.query).get("before")).toBe(
      "2026-11-12T10:00:00.000Z",
    );
    expect("query" in built && new URLSearchParams(built.query).get("before_id")).toBe(
      "00000000-0000-0000-0000-0000000000b2",
    );
  });

  it("sends an actor UUID as actor and a name or email as actor_q", () => {
    const byId = buildAuditQuery({ ...EMPTY, actor: "00000000-0000-0000-0000-0000000000a1" }, null);
    expect("query" in byId && new URLSearchParams(byId.query).get("actor")).toBe(
      "00000000-0000-0000-0000-0000000000a1",
    );
    const byName = buildAuditQuery({ ...EMPTY, actor: " chanda@example.test " }, null);
    expect("query" in byName && new URLSearchParams(byName.query).get("actor_q")).toBe(
      "chanda@example.test",
    );
    expect("query" in byName && new URLSearchParams(byName.query).has("actor")).toBe(false);
  });

  it("refuses malformed IDs and wildcard actions instead of sending them", () => {
    expect(buildAuditQuery({ ...EMPTY, actor: "x" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, entityId: "123" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, action: "admin%" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, entityType: "Order;drop" }, null)).toEqual({
      invalid: true,
    });
  });
});

describe("diffRows", () => {
  it("lists only changed fields, by dotted path", () => {
    expect(
      diffRows(
        { status: "pending", note: "same", meta: { tier: 1, kept: true } },
        { status: "approved", note: "same", meta: { tier: 2, kept: true }, added: "x" },
      ),
    ).toEqual([
      { key: "added", before: undefined, after: "x" },
      { key: "meta.tier", before: 1, after: 2 },
      { key: "status", before: "pending", after: "approved" },
    ]);
  });

  it("treats a creation as every field added and scalars as one value row", () => {
    expect(diffRows(null, { enabled: true })).toEqual([
      { key: "enabled", before: undefined, after: true },
    ]);
    expect(diffRows("a", "b")).toEqual([{ key: "value", before: "a", after: "b" }]);
    expect(diffRows({ a: [1] }, { a: [1] })).toEqual([]);
  });

  it("formats values for display", () => {
    expect(formatDiffValue(undefined)).toBe("");
    expect(formatDiffValue("text")).toBe("text");
    expect(formatDiffValue({ a: 1 })).toBe('{"a":1}');
  });
});

describe("entityKey", () => {
  const base: AuditEntry = {
    id: "a1",
    at: "2026-11-19T16:35:25Z",
    actor: null,
    actor_roles: null,
    action: "config.feature_flag.update",
    entity_type: "feature_flag",
    entity_id: null,
    outcome: "success",
    request_id: null,
    reason: null,
    before: { enabled: false, entity_key: "vendor_weekly_digest" },
    after: { enabled: true, entity_key: "vendor_weekly_digest" },
  };

  it("returns the text key stored for flags and config", () => {
    expect(entityKey(base)).toBe("vendor_weekly_digest");
  });

  it("returns null when no key is stored", () => {
    expect(entityKey({ ...base, before: null, after: { enabled: true } })).toBeNull();
  });
});
