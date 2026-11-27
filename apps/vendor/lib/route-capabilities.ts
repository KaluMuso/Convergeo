import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

import { parseStringAllowlist } from "./feature-flags";

const INTAKE_FLAG = "waha_vendor_intake";
const INTAKE_ALLOWLIST_KEY = "waha_intake_vendor_allowlist";
const CLIPS_FLAG = "clips";
const BUNDLES_FLAG = "bundles";
const COUPONS_FLAG = "coupons";

const CAPABILITY_FLAGS = [CLIPS_FLAG, BUNDLES_FLAG, COUPONS_FLAG, INTAKE_FLAG] as const;

/**
 * `feature_flags` is world-readable (RLS `feature_flags_select_public`) and flips rarely,
 * but the layout used to run four separate queries on every request. One batched read,
 * shared across concurrent callers and reused for a short window, takes four Supabase
 * round trips off the critical path of every vendor page render. Failures are never
 * cached (fail closed), so a transient error self-heals on the next request.
 */
export const FLAG_CACHE_TTL_MS = 30_000;

type Supabase = ReturnType<typeof createServerClient>;
type FlagMap = Record<string, boolean>;

let flagCache: { at: number; flags: FlagMap } | null = null;
let flagInflight: Promise<FlagMap | null> | null = null;

/** Test hook: drop the module-level cache. */
export function resetCapabilityFlagCache(): void {
  flagCache = null;
  flagInflight = null;
}

async function fetchCapabilityFlags(supabase: Supabase): Promise<FlagMap | null> {
  try {
    const { data, error } = await supabase
      .from("feature_flags")
      .select("flag, enabled")
      .in("flag", [...CAPABILITY_FLAGS]);
    if (error || !Array.isArray(data)) {
      return null;
    }
    const flags: FlagMap = {};
    for (const flag of CAPABILITY_FLAGS) {
      flags[flag] = false;
    }
    for (const row of data as Array<{ flag: string; enabled: unknown }>) {
      flags[row.flag] = Boolean(row.enabled);
    }
    return flags;
  } catch {
    return null;
  }
}

async function readCapabilityFlag(supabase: Supabase, flag: string): Promise<boolean> {
  const now = Date.now();
  if (flagCache && now - flagCache.at < FLAG_CACHE_TTL_MS) {
    return flagCache.flags[flag] ?? false;
  }
  if (!flagInflight) {
    flagInflight = fetchCapabilityFlags(supabase).finally(() => {
      flagInflight = null;
    });
  }
  const flags = await flagInflight;
  if (!flags) {
    return false;
  }
  flagCache = { at: Date.now(), flags };
  return flags[flag] ?? false;
}

async function resolveVendorIdForUser(
  supabase: Supabase,
  userId: string | null,
): Promise<string | null> {
  if (!userId) {
    return null;
  }
  try {
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

async function flagAccessible(flag: string): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    return await readCapabilityFlag(supabase, flag);
  } catch {
    return false;
  }
}

/** Whether the vendor Clips studio route may render (server-side, fail closed). */
export async function isClipsRouteAccessible(): Promise<boolean> {
  return flagAccessible(CLIPS_FLAG);
}

/** Whether the vendor offers (W8 bundles) route may render (server-side, fail closed). */
export async function isBundlesRouteAccessible(): Promise<boolean> {
  return flagAccessible(BUNDLES_FLAG);
}

/** Whether the vendor intake route may render (flag + allowlist, fail closed). */
export async function isIntakeRouteAccessible(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const intakeFlagOn = await readCapabilityFlag(supabase, INTAKE_FLAG);
    if (!intakeFlagOn) {
      return false;
    }

    // Per-vendor from here on: never cached.
    const {
      data: { user },
    } = await supabase.auth.getUser();
    const [vendorId, allowlistRow] = await Promise.all([
      resolveVendorIdForUser(supabase, user?.id ?? null),
      supabase
        .from("platform_config")
        .select("value")
        .eq("key", INTAKE_ALLOWLIST_KEY)
        .maybeSingle(),
    ]);
    if (!vendorId) {
      return false;
    }
    const allowlist = parseStringAllowlist(allowlistRow.data?.value);
    if (allowlist.length === 0) {
      return false;
    }
    return allowlist.includes(vendorId);
  } catch {
    return false;
  }
}

/** Whether the vendor coupons page may render (`feature_flags.coupons`, fail closed). */
export async function isCouponsRouteAccessible(): Promise<boolean> {
  return flagAccessible(COUPONS_FLAG);
}
