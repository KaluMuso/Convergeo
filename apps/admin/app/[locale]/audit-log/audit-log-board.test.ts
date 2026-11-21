import { describe, expect, it } from "vitest";

import {
  buildAuditQuery,
  entityKey,
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
      "2026-11-12T10:00:00.000Z",
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
  });

  it("refuses malformed IDs and wildcard actions instead of sending them", () => {
    expect(buildAuditQuery({ ...EMPTY, actor: "not-a-uuid" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, entityId: "123" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, action: "admin%" }, null)).toEqual({ invalid: true });
    expect(buildAuditQuery({ ...EMPTY, entityType: "Order;drop" }, null)).toEqual({
      invalid: true,
    });
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
