import { probeApiRoute } from "./api-route-probe";
import { isClipsRouteAccessible, isIntakeRouteAccessible } from "./route-capabilities";

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
  };
}

/**
 * Resolve vendor navigation capabilities for the current request.
 *
 * Sources (fail closed):
 * - `feature_flags.clips`, `feature_flags.waha_vendor_intake` via Supabase
 * - `platform_config.waha_intake_vendor_allowlist` for intake (authenticated)
 * - Anonymous API probes for routes that may lag deploy (`/rfq`, `/jobs`, payouts, pickup)
 */
export async function resolveVendorNavCapabilities(): Promise<VendorNavCapabilities> {
  const caps = coreCapabilities();

  try {
    const [clips, intake, rfq, jobs, payouts, scan] = await Promise.all([
      isClipsRouteAccessible(),
      isIntakeRouteAccessible(),
      probeApiRoute("/rfq"),
      probeApiRoute("/jobs"),
      probeApiRoute("/vendor/payouts"),
      probeApiRoute("/vendor/pickup/verify"),
    ]);

    caps.clips = clips;
    caps.intake = intake;
    caps.rfq = rfq;
    caps.jobs = jobs;
    caps.payouts = payouts;
    caps.scan = scan;

    for (const key of CORE_VISIBLE) {
      caps[key] = true;
    }
  } catch {
    for (const key of CORE_VISIBLE) {
      caps[key] = true;
    }
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
