import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

import { probeApiRoute } from "./api-route-probe";
import { parseStringAllowlist, readFeatureFlag } from "./feature-flags";

import type { VendorNavItemKey } from "../app/[locale]/_components/vendor-nav-config";

/** Per-item visibility resolved once per request on the server. */
export type VendorNavCapabilities = Record<VendorNavItemKey, boolean>;

const INTAKE_FLAG = "waha_vendor_intake";
const INTAKE_ALLOWLIST_KEY = "waha_intake_vendor_allowlist";
const CLIPS_FLAG = "clips";

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

async function resolveIntakeVisible(
  intakeFlagOn: boolean,
  vendorId: string | null,
): Promise<boolean> {
  if (!intakeFlagOn) {
    return false;
  }
  if (!vendorId) {
    return false;
  }

  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const { data } = await supabase
      .from("platform_config")
      .select("value")
      .eq("key", INTAKE_ALLOWLIST_KEY)
      .maybeSingle();
    const allowlist = parseStringAllowlist(data?.value);
    if (allowlist.length === 0) {
      return false;
    }
    return allowlist.includes(vendorId);
  } catch {
    return false;
  }
}

async function resolveVendorIdForUser(userId: string | null): Promise<string | null> {
  if (!userId) {
    return null;
  }
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const { data } = await supabase
      .from("vendors")
      .select("id")
      .eq("owner_id", userId)
      .maybeSingle();
    return typeof data?.id === "string" ? data.id : null;
  } catch {
    return null;
  }
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
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const {
      data: { user },
    } = await supabase.auth.getUser();

    const [clips, intakeFlag, rfq, jobs, payouts, scan] = await Promise.all([
      readFeatureFlag(supabase, CLIPS_FLAG),
      readFeatureFlag(supabase, INTAKE_FLAG),
      probeApiRoute("/rfq"),
      probeApiRoute("/jobs"),
      probeApiRoute("/vendor/payouts"),
      probeApiRoute("/vendor/pickup/verify"),
    ]);

    caps.clips = clips;
    caps.rfq = rfq;
    caps.jobs = jobs;
    caps.payouts = payouts;
    caps.scan = scan;

    const vendorId = await resolveVendorIdForUser(user?.id ?? null);
    caps.intake = await resolveIntakeVisible(intakeFlag, vendorId);

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
