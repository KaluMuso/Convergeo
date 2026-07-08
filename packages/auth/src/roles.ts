import type { User } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";

export type AppRole = "customer" | "vendor" | "admin";

const APP_ROLES = new Set<AppRole>(["customer", "vendor", "admin"]);

/**
 * Fast-path role read for middleware gating.
 * Reads `app_metadata.roles` from the Supabase user object (JWT-backed).
 * Authoritative role checks for mutations belong in the API (M04-P02), which
 * reads `public.user_roles` — never trust JWT claims alone for admin actions.
 */
export function getRolesFromUser(user: User | null | undefined): AppRole[] {
  if (!user) {
    return [];
  }

  const metadataRoles = user.app_metadata?.roles;
  if (!Array.isArray(metadataRoles)) {
    return [];
  }

  return metadataRoles.filter((role): role is AppRole => {
    return typeof role === "string" && APP_ROLES.has(role as AppRole);
  });
}

export function hasRole(roles: readonly string[], required: AppRole): boolean {
  return roles.includes(required);
}

/**
 * Authoritative role read from `public.user_roles` via the Supabase server client.
 * Use in Server Components / route handlers — not in edge middleware (no DB round-trip).
 */
export async function getRoles(supabase: SupabaseClient, userId: string): Promise<AppRole[]> {
  const { data, error } = await supabase.from("user_roles").select("role").eq("user_id", userId);

  if (error) {
    throw error;
  }

  return (data ?? [])
    .map((row) => row.role)
    .filter((role): role is AppRole => typeof role === "string" && APP_ROLES.has(role as AppRole));
}
