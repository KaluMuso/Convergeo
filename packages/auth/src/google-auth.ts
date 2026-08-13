export type GoogleAuthEnvBag = {
  NEXT_PUBLIC_GOOGLE_AUTH_ENABLED?: string;
};

/**
 * Google OAuth is fail-closed. The button is operational only when
 * `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` is the exact string `"true"`.
 *
 * Direct `process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` access is required so
 * Next.js inlines the flag into client bundles. Do not enable the provider in
 * Supabase from this module.
 */
export function isGoogleAuthEnabled(env: GoogleAuthEnvBag = {}): boolean {
  const configured =
    env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED ?? process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED;
  return configured === "true";
}
