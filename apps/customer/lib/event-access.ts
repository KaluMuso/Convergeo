/** A cookie-safe, deterministic name for a short-lived private event proof. */
export function eventAccessCookieName(slug: string): string {
  // Event slugs are already URL-safe. Keep this defensive so a malformed route
  // segment cannot turn into an invalid Set-Cookie header.
  return `event-access-${slug.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 96)}`;
}
