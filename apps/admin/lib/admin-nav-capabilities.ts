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
  const any = (...wanted: string[]) => wanted.some(has);
  return {
    home: has("analytics.read"),
    // Analytics dashboards: operational tabs need analytics.read, money tabs finance.read (D3).
    analytics: any("analytics.read", "finance.read", "finance.operate"),
    kyc: has("vendors.manage"),
    moderation: has("products.manage"),
    disputes: any("finance.operate", "support.manage"),
    support: has("support.manage"),
    intake: has("vendors.manage"),
    orders: any("finance.read", "finance.operate"),
    business: has("vendors.manage"),
    merch: has("ads.manage"),
    homeFeed: has("ads.manage"),
    advertising: has("ads.manage"),
    clips: unrestricted,
    events: has("events.manage"),
    config: unrestricted,
    translations: unrestricted,
    theme: unrestricted,
    roles: canManageRoles,
    accounts: canManageRoles,
    // Never implied by `unrestricted`: the API withholds audit.read from legacy admin.
    auditLog: permissions.includes("audit.read"),
    services: any("services.read", "services.manage"),
    inventory: has("inventory.read"),
  };
}
