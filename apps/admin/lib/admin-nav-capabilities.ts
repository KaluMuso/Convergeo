import type { AdminNavItemKey } from "../app/[locale]/_components/admin-nav-config";

/**
 * Admin navigation capabilities.
 *
 * Unlike vendor nav, operational admin tools (clips moderation, WhatsApp intake
 * review, config/flags) remain visible while public/vendor flags are OFF so
 * administrators can prepare, moderate, and support disabled capabilities.
 */
export type AdminNavCapabilities = Record<AdminNavItemKey, boolean>;

/**
 * All admin destinations are operational — no public-feature gating — except
 * `analytics` (Convergeo Intelligence 1B-05), which starts hidden and is revealed by
 * the shell only when `/admin/analytics/status` reports the rollups flag ON.
 */
export function resolveAdminNavCapabilities(): AdminNavCapabilities {
  return {
    home: true,
    analytics: false,
    kyc: true,
    moderation: true,
    disputes: true,
    support: true,
    intake: true,
    orders: true,
    business: true,
    merch: true,
    clips: true,
    events: true,
    config: true,
    translations: true,
    theme: true,
  };
}
