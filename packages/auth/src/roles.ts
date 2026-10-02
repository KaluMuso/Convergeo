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
 * Extracts roles from VERIFIED JWT claims (`supabase.auth.getClaims()`'s
 * `data.claims`) — the middleware routing/gating fast path.
 *
 * The Custom Access Token Hook (`0051_custom_access_token_role_hook.sql`)
 * writes `public.user_roles` into `claims.app_metadata.roles` on every token
 * mint. That is a DIFFERENT object from the Supabase `User.app_metadata`
 * returned by `getUser()`/`getSession()`: the hook mutates the issued
 * token's claims, never `auth.users.raw_app_meta_data` — so
 * `getRolesFromUser()` (which reads the User object) can never see roles
 * granted this way. Middleware gating must read the verified claims
 * directly instead.
 *
 * Fails closed (`[]`) on any malformed input rather than throwing — a
 * claims shape that doesn't match expectations must never be treated as
 * "no restriction", only as "no roles". Never reads `user_metadata`: that
 * field is user-editable in some Supabase configurations and must never be
 * able to confer a role.
 */
export function getRolesFromClaims(claims: unknown): AppRole[] {
  if (!claims || typeof claims !== "object") {
    return [];
  }

  const appMetadata = (claims as { app_metadata?: unknown }).app_metadata;
  if (!appMetadata || typeof appMetadata !== "object") {
    return [];
  }

  const roles = (appMetadata as { roles?: unknown }).roles;
  if (!Array.isArray(roles)) {
    return [];
  }

  return roles.filter((role): role is AppRole => {
    return typeof role === "string" && APP_ROLES.has(role as AppRole);
  });
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
