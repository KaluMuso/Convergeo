import { describe, expect, it } from "vitest";

import { getAdminTranslator } from "./admin-translator";

// Regression for the live production bug: `getTranslations("admin.xxx")` from
// next-intl/server reads the ambient request-config messages, which ship
// `common` alone (packages/i18n/src/request.ts) — the "admin" namespace was
// never loaded there, so every admin page header silently fell back to the
// raw key ("title", "subtitle") in production (MISSING_MESSAGE: admin.dashboard,
// 238 occurrences). getAdminTranslator must resolve the *real* message.
describe("getAdminTranslator", () => {
  it("resolves a real translated string, not a raw key fallback", async () => {
    const t = await getAdminTranslator("en", "admin.dashboard");

    expect(t("title")).toBe("Operations dashboard");
    expect(t("title")).not.toBe("title");
    expect(t("subtitle")).not.toBe("subtitle");
  });

  it("resolves a different admin sub-namespace independently", async () => {
    const t = await getAdminTranslator("en", "admin.orders");

    expect(t("title")).toBe("Order operations");
    expect(t("title")).not.toBe("title");
  });
});
