import { describe, expect, it } from "vitest";

import bem from "../../../packages/i18n/messages/bem/common.json";
import en from "../../../packages/i18n/messages/en/common.json";
import fr from "../../../packages/i18n/messages/fr/common.json";

import { codTrustLine } from "./cod-trust";

describe("codTrustLine", () => {
  it("resolves the line from getMessages-shaped input (common at the root) in every locale", () => {
    expect(codTrustLine("en", { common: en })).toBe(en.codTrust.line);
    expect(codTrustLine("fr", { common: fr })).toBe(fr.codTrust.line);
    expect(codTrustLine("bem", { common: bem })).toBe(bem.codTrust.line);
  });

  it("never returns the raw key for a real locale", () => {
    expect(codTrustLine("en", { common: en })).not.toMatch(/codTrust/);
  });
});
