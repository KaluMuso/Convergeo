import { describe, expect, it, beforeEach } from "vitest";

import {
  clearMessageCache,
  getLoadedNamespaceKeys,
  loadNamespace,
  resolveMessage,
} from "./request";

describe("resolveMessage", () => {
  beforeEach(() => {
    clearMessageCache();
  });

  it("falls back to English for missing locale files", async () => {
    const message = await resolveMessage("bem", "app.name");
    expect(message).toBe("Vergeo5");
  });

  it("falls back to the key when missing in all locales", async () => {
    const message = await resolveMessage("en", "missing.key");
    expect(message).toBe("missing.key");
  });

  it("renders ICU-style interpolation", async () => {
    const message = await resolveMessage("en", "greeting", { name: "Vergeo" });
    expect(message).toBe("Hello, Vergeo!");
  });

  it("falls back to English per namespace for missing locale namespace files", async () => {
    const message = await resolveMessage("nya", "auth.login.title");
    expect(message).toBe("Sign in");
  });

  it("resolves namespaced keys", async () => {
    const message = await resolveMessage("en", "catalog.title");
    expect(message).toBe("Browse products");
  });
});

describe("loadNamespace", () => {
  beforeEach(() => {
    clearMessageCache();
  });

  it("loads only the requested namespace on demand", async () => {
    const auth = await loadNamespace("en", "auth");
    expect(auth["auth.login.title"]).toBe("Sign in");
    expect(getLoadedNamespaceKeys()).toEqual(["en:auth"]);
    expect(getLoadedNamespaceKeys()).not.toContain("en:catalog");
  });

  it("falls back to English when locale namespace file is missing", async () => {
    const auth = await loadNamespace("bem", "auth");
    expect(auth["auth.login.title"]).toBe("Sign in");
    expect(getLoadedNamespaceKeys()).toContain("en:auth");
  });
});
