import type { AdminNavItemKey } from "../app/[locale]/_components/admin-nav-config";

/**
 * Admin navigation capabilities.
 *
 * Unlike vendor nav, operational admin tools (clips moderation, WhatsApp intake
 * review, config/flags) remain visible while public/vendor flags are OFF so
 * administrators can prepare, moderate, and support disabled capabilities.
 */
export type AdminNavCapabilities = Record<AdminNavItemKey, boolean>;

/** The API returns current grants; fail closed while they are unavailable. */
export function resolveAdminNavCapabilities(
  permissions: readonly string[] = [],
  unrestricted = false,
  canManageRoles = false,
): AdminNavCapabilities {
  const has = (permission: string) => unrestricted || permissions.includes(permission);
  return {
    home: has("analytics.read"),
    kyc: has("vendors.manage"),
    moderation: has("products.manage"),
    disputes: unrestricted,
    support: unrestricted,
    intake: has("vendors.manage"),
    orders: has("finance.read"),
    business: has("vendors.manage"),
    merch: has("ads.manage"),
    clips: unrestricted,
    events: has("events.manage"),
    config: unrestricted,
    translations: unrestricted,
    theme: unrestricted,
    roles: canManageRoles,
    services: has("services.read"),
    inventory: has("inventory.read"),
  };
}
