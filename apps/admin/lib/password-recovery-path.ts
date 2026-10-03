import { LOCALES } from "@vergeo/i18n";

/** Only the two recovery pages skip app-role gating; Cloudflare Access still applies. */
export function isAdminPasswordRecoveryPath(pathname: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return LOCALES.some(
    (locale) =>
      path === `/${locale}/reset-password` || path === `/${locale}/reset-password/confirm`,
  );
}
