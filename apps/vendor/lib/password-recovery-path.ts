import { LOCALES } from "@vergeo/i18n";

/** Only recovery pages skip vendor-role gating; privileged vendor routes stay gated. */
export function isVendorPasswordRecoveryPath(pathname: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return LOCALES.some(
    (locale) =>
      path === `/${locale}/reset-password` ||
      path === `/${locale}/reset-password/confirm`,
  );
}

/** Public, purpose-bound Auth setup pages; operational routes remain role-gated. */
export function isVendorAuthSetupPath(pathname: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return (
    isVendorPasswordRecoveryPath(pathname) ||
    LOCALES.some((locale) => path === `/${locale}/accept-invite`)
  );
}
