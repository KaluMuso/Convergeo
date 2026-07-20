import { describe, expect, it, beforeEach } from "vitest";

import {
  clearMessageCache,
  getLoadedNamespaceKeys,
  loadNamespace,
  resolveMessage,
} from "./request";

type AuthMessages = {
  login: { title: string };
};

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
    const auth = (await loadNamespace("en", "auth")) as AuthMessages;
    expect(auth.login.title).toBe("Sign in");
    expect(getLoadedNamespaceKeys()).toEqual(["en:auth"]);
    expect(getLoadedNamespaceKeys()).not.toContain("en:catalog");
  });

  it("loads bem auth overlay with translated login title", async () => {
    const auth = (await loadNamespace("bem", "auth")) as AuthMessages;
    expect(auth.login.title).toBe("Ingilani");
    expect(getLoadedNamespaceKeys()).toContain("bem:auth");
  });

  it("falls back to English when locale namespace file is missing", async () => {
    const admin = (await loadNamespace("bem", "admin")) as { title?: string };
    expect(admin).toBeTruthy();
    expect(getLoadedNamespaceKeys()).toContain("en:admin");
  });

  it("deep-merges Phase-1 bem catalog over English for non-critical keys", async () => {
    const catalog = await loadNamespace("bem", "catalog");
    const home = catalog.home as { hero: { escrowStep1: string }; flash?: { defaultTag: string } };
    expect(home.hero.escrowStep1).not.toBe("You pay");
    // Non-critical flash copy still available via English merge.
    expect(home.flash?.defaultTag).toBeTruthy();
  });
});
