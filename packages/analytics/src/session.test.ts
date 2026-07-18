import { beforeEach, describe, expect, it } from "vitest";

import { __resetSessionMemory, getSessionId } from "./session";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const STORAGE_KEY = "vg_session_id";

describe("getSessionId", () => {
  beforeEach(() => {
    window.localStorage.clear();
    __resetSessionMemory();
  });

  it("generates and persists a stable opaque uuid", () => {
    const first = getSessionId();
    expect(first).toMatch(UUID_V4);
    expect(getSessionId()).toBe(first); // stable across calls
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(first);
  });

  it("reuses an existing valid id from storage", () => {
    window.localStorage.setItem(STORAGE_KEY, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(getSessionId()).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  });

  it("replaces a malformed stored id", () => {
    window.localStorage.setItem(STORAGE_KEY, "not-a-uuid");
    const id = getSessionId();
    expect(id).not.toBe("not-a-uuid");
    expect(id).toMatch(UUID_V4);
  });

  it("falls back to a stable in-memory id when storage throws", () => {
    const original = Object.getOwnPropertyDescriptor(Storage.prototype, "getItem");
    Object.defineProperty(window.localStorage, "getItem", {
      configurable: true,
      value: () => {
        throw new Error("storage blocked");
      },
    });
    try {
      const first = getSessionId();
      const second = getSessionId();
      expect(first).toBe(second); // stable per tab even without storage
      expect(first).toMatch(UUID_V4);
    } finally {
      if (original) {
        Object.defineProperty(window.localStorage, "getItem", original);
      }
    }
  });
});
