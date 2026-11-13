import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";

import accountMessages from "../../../packages/i18n/messages/en/account.json";
import catalogMessages from "../../../packages/i18n/messages/en/catalog.json";
import directoryMessages from "../../../packages/i18n/messages/en/directory.json";
import { catalogLogisticsLabels } from "../app/[locale]/(shop)/_components/plp/logistics-pills";

/**
 * next-intl renders the key path ("catalog.plp.card.pill.nearest") when a
 * message with placeholders is read through `t()` without values. Labels that
 * the client fills in itself must therefore be read with `t.raw()`. These pin
 * the behaviour the pages rely on.
 */
describe("client-filled message templates", () => {
  const catalog = createTranslator({
    locale: "en",
    messages: { catalog: catalogMessages },
    namespace: "catalog",
    onError: () => undefined,
  });

  it("t() without values yields the key path, which is why raw is required", () => {
    expect(catalog("plp.card.pill.nearest")).toBe("catalog.plp.card.pill.nearest");
    expect(String(catalog.raw("plp.card.pill.nearest"))).toContain("{distance}");
  });

  it("logistics pill labels carry a fillable distance template, never a key path", () => {
    const labels = catalogLogisticsLabels(
      catalog as unknown as Parameters<typeof catalogLogisticsLabels>[0],
    );

    expect(labels.nearest).toContain("{distance}");
    expect(labels.nearest).not.toContain("plp.card");
    expect(labels.nearest.replace("{distance}", "2 km")).not.toContain("{");
  });

  it("the vendor card rating template is filled by matching the whole ICU argument", () => {
    const template = directoryMessages.card.rating;
    const filled = template.replace(/\{rating[^}]*\}/, "4.5").replace("{count}", "12");

    expect(filled).not.toMatch(/[{}]/);
    expect(filled).toContain("4.5");
    expect(filled).toContain("12");
  });

  it("address templates stay fillable", () => {
    const account = createTranslator({
      locale: "en",
      messages: { account: accountMessages },
      namespace: "account",
      onError: () => undefined,
    });

    expect(String(account.raw("addresses.coordsTemplate"))).toBe("{lat}, {lng}");
    expect(String(account.raw("addresses.mapAlt"))).toContain("{lat}");
  });
});
