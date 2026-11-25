import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

/** Read ``social_contacts`` fresh; fail closed (matches clips route). */
export async function socialContactsEnabled(): Promise<boolean> {
  try {
    const cookieStore = await cookies();
    const supabase = createServerClient(cookieStore);
    const { data } = await supabase
      .from("feature_flags")
      .select("enabled")
      .eq("flag", "social_contacts")
      .maybeSingle();
    return Boolean(data?.enabled);
  } catch {
    return false;
  }
}
