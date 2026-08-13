export {
  createBrowserClient,
  getBrowserAccessToken,
  resetBrowserClientForTests,
} from "./browser-client";
export { createCookieMethods, createServerClient } from "./server-client";
export {
  createLoginRedirect,
  createPortalRedirect,
  getLocaleFromPath,
  isAdminBypassActive,
  isAdminPermissionDeniedPath,
  isAuthExemptPath,
  isVendorOnboardingPath,
  mergeSessionCookies,
  resolveGatedRedirect,
  shouldRedirectToLogin,
  updateSession,
  type AuthGate,
  type GatedRedirectKind,
  type UpdateSessionResult,
} from "./middleware";
export { useSession, type UseSessionResult } from "./use-session";
export { getRoles, getRolesFromUser, hasRole, type AppRole } from "./roles";
export { AUTH_PORTALS, isAuthPortal, type AuthPortal } from "./portal";
export { isGoogleAuthEnabled, type GoogleAuthEnvBag } from "./google-auth";
export {
  adminPermissionDeniedPath,
  defaultPortalHomePath,
  sanitizeNextPath,
  vendorOnboardingPath,
} from "./safe-next";
