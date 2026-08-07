import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const messagesRoot = join(here, "../../../packages/i18n/messages");

function loadJson(locale: string, namespace: string): Record<string, unknown> {
  const raw = readFileSync(join(messagesRoot, locale, `${namespace}.json`), "utf8");
  return JSON.parse(raw) as Record<string, unknown>;
}

const SHELL_NAV_KEYS = [
  "ariaLabel",
  "desktopAriaLabel",
  "home",
  "listings",
  "orders",
  "profile",
  "more",
  "scan",
  "returns",
  "analytics",
  "services",
  "events",
  "rfq",
  "jobs",
  "clips",
  "reviews",
  "payouts",
  "disputes",
  "intake",
] as const;

const SHELL_GROUP_KEYS = ["operate", "sell", "business"] as const;

describe("vendor shell i18n structure", () => {
  for (const locale of ["bem", "nya"] as const) {
    it(`includes UX-01 shell keys for ${locale}`, () => {
      const vendor = loadJson(locale, "vendor");
      const shell = vendor.shell as Record<string, unknown>;
      const nav = shell.nav as Record<string, unknown>;
      const groups = shell.groups as Record<string, unknown>;
      const moreMenu = shell.moreMenu as Record<string, unknown>;

      for (const key of SHELL_NAV_KEYS) {
        expect(nav[key], `vendor.shell.nav.${key}`).toBeTruthy();
      }
      for (const key of SHELL_GROUP_KEYS) {
        expect(groups[key], `vendor.shell.groups.${key}`).toBeTruthy();
      }
      expect(moreMenu.title).toBeTruthy();
      expect(moreMenu.close).toBeTruthy();
    });
  }
});

describe("account vendor portal handoff i18n structure", () => {
  for (const locale of ["bem", "nya", "en"] as const) {
    it(`includes vendor portal hub keys for ${locale}`, () => {
      const account = loadJson(locale, "account");
      const hub = account.hub as Record<string, unknown>;
      expect(hub.vendorPortalTitle).toBeTruthy();
      expect(hub.vendorPortalBody).toBeTruthy();
      expect(hub.vendorPortalCta).toBeTruthy();
    });
  }
});
