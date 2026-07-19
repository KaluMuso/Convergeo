import { describe, expect, it } from "vitest";

import en from "../../../../../../../packages/i18n/messages/en/checkout.json";
import fr from "../../../../../../../packages/i18n/messages/fr/checkout.json";
import zh from "../../../../../../../packages/i18n/messages/zh/checkout.json";

/**
 * LB-P2-04 — cart free-delivery nudge must not claim unconditional free shipping.
 * Copy must keep Lusaka/zone scope and avoid “unlocked paid delivery” overclaims.
 */
describe("free-delivery honesty i18n (LB-P2-04)", () => {
  it.each([
    ["en", en.cart],
    ["fr", fr.cart],
    ["zh", zh.cart],
  ] as const)("%s cart delivery keys stay scoped", (_locale, cart) => {
    expect(cart.deliveryThreshold).toContain("{threshold}");
    expect(cart.deliveryScopeNote.length).toBeGreaterThan(20);
    expect(cart.freeDeliveryProgress).toContain("{threshold}");
    expect(cart.deliveryHint).toContain("{amount}");
    // Must not hardcode a bare "K200" threshold claim anymore.
    expect(cart.deliveryThreshold).not.toMatch(/K200(?![.\d])/);
  });

  it("English copy names Lusaka and defers zone confirmation", () => {
    expect(en.cart.deliveryThreshold.toLowerCase()).toContain("lusaka");
    expect(en.cart.deliveryEligible.toLowerCase()).toContain("checkout");
    expect(en.cart.deliveryScopeNote.toLowerCase()).toContain("pickup");
  });
});
