/** Parse `platform_config.value` when it stores a JSON string array. */
export function parseStringAllowlist(raw: unknown): string[] {
  let value = raw;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

async function readFeatureFlag(
  supabase: ReturnType<typeof import("@vergeo/auth/server-client").createServerClient>,
  flag: string,
): Promise<boolean> {
  try {
    const { data } = await supabase
      .from("feature_flags")
      .select("enabled")
      .eq("flag", flag)
      .maybeSingle();
    return Boolean(data?.enabled);
  } catch {
    return false;
  }
}

export { readFeatureFlag };
