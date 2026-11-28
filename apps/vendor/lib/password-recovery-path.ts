import { LOCALES } from "@vergeo/i18n";

/** Only recovery pages skip vendor-role gating; privileged vendor routes stay gated. */
export function isVendorPasswordRecoveryPath(pathname: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return LOCALES.some(
    (locale) =>
      path === `/${locale}/reset-password` || path === `/${locale}/reset-password/confirm`,
  );
}

/**
 * Public, purpose-bound Auth setup pages; operational routes remain role-gated.
 * `/signup` is the self-serve seller sign-up: it only creates a plain account,
 * which still has to pass onboarding + KYC before it gets the vendor role.
 */
export function isVendorAuthSetupPath(pathname: string): boolean {
  const path = pathname.replace(/\/$/, "");
  return (
    isVendorPasswordRecoveryPath(pathname) ||
    LOCALES.some((locale) => path === `/${locale}/accept-invite` || path === `/${locale}/signup`)
  );
}
