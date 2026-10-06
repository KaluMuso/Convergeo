import { createTranslator } from "next-intl";
import { describe, expect, it, beforeEach } from "vitest";

import { LOCALES } from "./locales";
import {
  NAMESPACES,
  clearMessageCache,
  expandDottedKeys,
  getLoadedNamespaceKeys,
  loadMessages,
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
    expect(message).toBe("Convergeo");
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

  it("expands legacy dotted keys before handing messages to next-intl", async () => {
    const catalog = await loadNamespace("en", "catalog");
    const checkout = await loadNamespace("en", "checkout");
    const bemCheckout = await loadNamespace("bem", "checkout");

    expect(catalog).toMatchObject({ catalog: { title: "Browse products" } });
    expect(checkout).toMatchObject({ checkout: { title: "Checkout", pageTitle: "Checkout" } });
    expect(bemCheckout).toMatchObject({ checkout: { title: "Ukushita" } });
    expect(Object.keys(catalog).some((key) => key.includes("."))).toBe(false);
    expect(Object.keys(checkout).some((key) => key.includes("."))).toBe(false);
    expect(await resolveMessage("bem", "checkout.title")).toBe("Ukushita");
    const tCatalog = createTranslator({
      locale: "en",
      messages: { catalog: catalog as { catalog: { title: string } } },
      namespace: "catalog",
    });
    expect(tCatalog("catalog.title")).toBe("Browse products");
  });

  it("passes no literal dotted key from any locale namespace to next-intl", async () => {
    const assertNestedKeys = (messages: Record<string, unknown>) => {
      for (const [key, value] of Object.entries(messages)) {
        expect(key).not.toContain(".");
        if (value !== null && typeof value === "object") {
          assertNestedKeys(value as Record<string, unknown>);
        }
      }
    };
    for (const locale of LOCALES) {
      for (const namespace of NAMESPACES) {
        assertNestedKeys(await loadNamespace(locale, namespace));
      }
    }
  });

  it("passes plain message objects across the server-to-client boundary", async () => {
    const assertSerializableMessages = (value: unknown): void => {
      if (typeof value === "string") return;
      expect(value).not.toBeNull();
      expect(Array.isArray(value)).toBe(false);
      expect(Object.getPrototypeOf(value)).toBe(Object.prototype);
      for (const child of Object.values(value as Record<string, unknown>)) {
        assertSerializableMessages(child);
      }
    };

    // The admin layout passes this same namespace bundle to a Client Component.
    assertSerializableMessages(await loadMessages("en", ["common", "admin", "services"]));
    for (const locale of LOCALES) {
      for (const namespace of NAMESPACES) {
        assertSerializableMessages(await loadNamespace(locale, namespace));
      }
    }
  });

  it("rejects colliding and unsafe message paths", () => {
    for (const messages of [
      { title: "A", "title.text": "B" },
      { title: { text: "A" }, "title.text": "B" },
      { "title.text": "B", title: { text: "A" } },
    ]) {
      expect(() => expandDottedKeys(messages)).toThrow("Message key collision: title.text");
    }
    for (const segment of ["__proto__", "constructor", "prototype"]) {
      expect(() => expandDottedKeys({ [`${segment}.polluted`]: "B" })).toThrow(
        `Unsafe message key: ${segment}.polluted`,
      );
    }
    expect(expandDottedKeys({ "toString.value": "A" })).toMatchObject({
      toString: { value: "A" },
    });
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
