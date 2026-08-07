import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

import { parseStringAllowlist, readFeatureFlag } from "./feature-flags";

const INTAKE_FLAG = "waha_vendor_intake";
const INTAKE_ALLOWLIST_KEY = "waha_intake_vendor_allowlist";
const CLIPS_FLAG = "clips";

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

/** Whether the vendor Clips studio route may render (server-side, fail closed). */
export async function isClipsRouteAccessible(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    return await readFeatureFlag(supabase, CLIPS_FLAG);
  } catch {
    return false;
  }
}

/** Whether the vendor intake route may render (flag + allowlist, fail closed). */
export async function isIntakeRouteAccessible(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const intakeFlagOn = await readFeatureFlag(supabase, INTAKE_FLAG);
    if (!intakeFlagOn) {
      return false;
    }

    const {
      data: { user },
    } = await supabase.auth.getUser();
    const vendorId = await resolveVendorIdForUser(user?.id ?? null);
    if (!vendorId) {
      return false;
    }

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
