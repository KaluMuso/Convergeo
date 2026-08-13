export const AUTH_PORTALS = ["customer", "vendor", "admin"] as const;

export type AuthPortal = (typeof AUTH_PORTALS)[number];

export function isAuthPortal(value: unknown): value is AuthPortal {
  return typeof value === "string" && (AUTH_PORTALS as readonly string[]).includes(value);
}
