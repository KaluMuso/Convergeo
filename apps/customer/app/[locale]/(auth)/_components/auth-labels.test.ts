import { describe, expect, it } from "vitest";

import bem from "../../../../../../packages/i18n/messages/bem/auth.json";
import en from "../../../../../../packages/i18n/messages/en/auth.json";
import fr from "../../../../../../packages/i18n/messages/fr/auth.json";
import nya from "../../../../../../packages/i18n/messages/nya/auth.json";
import zh from "../../../../../../packages/i18n/messages/zh/auth.json";
import { deepMergeMessages } from "../../../../../../packages/i18n/src/deep-merge";

import { createLoginLabels } from "./auth-labels";

describe("localized login error labels", () => {
  for (const [locale, auth] of Object.entries({ en, fr, bem, nya, zh })) {
    it.each(["customer", "vendor", "admin"] as const)(
      `${locale} supplies translated or English fallback labels for %s`,
      (variant) => {
        const merged = deepMergeMessages(en, auth);
        const labels = createLoginLabels(locale, { auth: merged }, { variant });
        expect(labels.phone.phoneHelp).toBe(auth.login.phoneHelp);
        expect(labels.phone.phoneHelp).not.toMatch(/SMS|WhatsApp|短信|短消息/i);
        expect(labels.phone.phoneHelp).toMatch(/email|e-mail|电子邮件/);
        expect(auth.signup.phoneHelp).not.toMatch(/SMS|WhatsApp|短信|短消息/i);
        expect(auth.signup.phoneHelp).toMatch(/email|e-mail|电子邮件/);
        expect(labels.email.network).toBe(
          "network" in auth.errors ? auth.errors.network : en.errors.network,
        );
        expect(labels.email.unavailable).toBe(
          "unavailable" in auth.errors ? auth.errors.unavailable : en.errors.unavailable,
        );
        expect(labels.email.throttled).toContain("{seconds}");
      },
    );
  }
});
