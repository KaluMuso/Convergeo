import { probeApiRoute } from "./api-route-probe";
import {
  isBundlesRouteAccessible,
  isClipsRouteAccessible,
  isCouponsRouteAccessible,
  isIntakeRouteAccessible,
} from "./route-capabilities";

import type { VendorNavItemKey } from "../app/[locale]/_components/vendor-nav-config";

/** Per-item visibility resolved once per request on the server. */
export type VendorNavCapabilities = Record<VendorNavItemKey, boolean>;

/** Core commerce surfaces — always shown unless capability resolution throws. */
const CORE_VISIBLE: VendorNavItemKey[] = [
  "home",
  "orders",
  "listings",
  "returns",
  "analytics",
  "services",
  "events",
  "reviews",
  "profile",
  "disputes",
  "settings",
  "extras",
];

function coreCapabilities(): VendorNavCapabilities {
  return {
    home: true,
    orders: true,
    listings: true,
    scan: false,
    returns: true,
    analytics: true,
    services: true,
    events: true,
    rfq: false,
    jobs: false,
    clips: false,
    reviews: true,
    profile: true,
    payouts: false,
    disputes: true,
    intake: false,
    coupons: false,
    settings: true,
    offers: false,
    extras: true,
  };
}

/**
 * Resolve vendor navigation capabilities for the current request.
 *
 * Sources (fail closed):
 * - `feature_flags.clips`, `feature_flags.waha_vendor_intake`, `feature_flags.bundles` via Supabase
 * - `platform_config.waha_intake_vendor_allowlist` for intake (authenticated)
 * - Anonymous API probes for routes that may lag deploy (`/rfq`, `/jobs`, payouts, pickup)
 */
export const NAV_CAPABILITIES_BUDGET_MS = 2000;

/**
 * The capability lookups only decide which optional nav entries appear, so they
 * must never hold up page render: past the budget we serve the core nav
 * (optional entries fail closed) instead of waiting on a slow probe.
 */
export async function resolveVendorNavCapabilities(): Promise<VendorNavCapabilities> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const budget = new Promise<VendorNavCapabilities>((resolve) => {
    timer = setTimeout(() => resolve(fallbackCapabilities()), NAV_CAPABILITIES_BUDGET_MS);
  });
  try {
    return await Promise.race([resolveCapabilitiesUnbounded(), budget]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/**
 * Last fully-resolved capabilities on this server. When a probe is slow, optional
 * entries (Offers, Payouts, Scan...) used to vanish from the nav until the next
 * request; serving what we last knew keeps them stable. The per-vendor intake entry
 * is never reused across requests, so it fails closed.
 */
let lastResolved: VendorNavCapabilities | null = null;

/** Test hook. */
export function resetLastResolvedCapabilities(): void {
  lastResolved = null;
}

function fallbackCapabilities(): VendorNavCapabilities {
  return lastResolved ? { ...lastResolved, intake: false } : coreCapabilities();
}

async function resolveCapabilitiesUnbounded(): Promise<VendorNavCapabilities> {
  const caps = coreCapabilities();
  let complete = false;

  try {
    const [clips, intake, rfq, jobs, payouts, scan, offers, coupons] = await Promise.all([
      isClipsRouteAccessible(),
      isIntakeRouteAccessible(),
      probeApiRoute("/rfq"),
      probeApiRoute("/jobs"),
      probeApiRoute("/vendor/payouts"),
      probeApiRoute("/vendor/pickup/verify"),
      isBundlesRouteAccessible(),
      isCouponsRouteAccessible(),
    ]);

    caps.clips = clips;
    caps.intake = intake;
    caps.rfq = rfq;
    caps.jobs = jobs;
    caps.payouts = payouts;
    caps.scan = scan;
    caps.offers = offers;
    caps.coupons = coupons;

    for (const key of CORE_VISIBLE) {
      caps[key] = true;
    }
    complete = true;
  } catch {
    for (const key of CORE_VISIBLE) {
      caps[key] = true;
    }
  }

  if (complete) {
    lastResolved = caps;
  }
  return caps;
}

/** Apply capability visibility to a nav item key. */
export function isVendorNavItemVisible(
  key: VendorNavItemKey,
  capabilities: VendorNavCapabilities,
): boolean {
  return capabilities[key];
}
