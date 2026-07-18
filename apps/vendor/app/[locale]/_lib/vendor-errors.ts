import { ApiError } from "@vergeo/config";

export type VendorLoadErrorKind = "auth" | "permission" | "not_found" | "network" | "unknown";

export type VendorLoadError = {
  kind: VendorLoadErrorKind;
  status: number;
  code: string;
};

/**
 * Classify API failures for vendor-scoped screens.
 * 401 → auth, 403 → permission (wrong role / not a vendor), 404 → not found.
 */
export function classifyVendorError(error: unknown): VendorLoadError {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.code === "unauthenticated") {
      return { kind: "auth", status: error.status, code: error.code };
    }
    if (error.status === 403 || error.code === "forbidden" || error.code === "not_vendor") {
      return { kind: "permission", status: error.status, code: error.code };
    }
    if (error.status === 404 || error.code === "not_found") {
      return { kind: "not_found", status: error.status, code: error.code };
    }
    if (error.status === 0 || error.code === "network_error") {
      return { kind: "network", status: error.status, code: error.code };
    }
    return { kind: "unknown", status: error.status, code: error.code };
  }
  return { kind: "unknown", status: 500, code: "unknown_error" };
}

export function vendorErrorMessageKey(
  error: unknown,
  scope: "home" | "profile" | "listings" | "onboarding" | "analytics" | "listingsManage",
): string {
  const classified = classifyVendorError(error);
  const listingsScope = scope === "listings" || scope === "listingsManage";
  switch (classified.kind) {
    case "auth":
      if (scope === "profile") return "profile.errors.authRequired";
      if (listingsScope) return "listings.errors.authRequired";
      if (scope === "onboarding") return "onboarding.errors.authRequired";
      if (scope === "analytics") return "analytics.errors.authRequired";
      return "home.errors.authRequired";
    case "permission":
      if (scope === "profile") return "profile.errors.permissionDenied";
      if (listingsScope) return "listings.errors.permissionDenied";
      if (scope === "onboarding") return "onboarding.errors.permissionDenied";
      if (scope === "analytics") return "analytics.errors.permissionDenied";
      return "home.errors.permissionDenied";
    case "not_found":
      if (listingsScope) return "listings.errors.notFound";
      if (scope === "profile") return "profile.errors.notFound";
      if (scope === "onboarding") return "onboarding.errors.notFound";
      return "home.errors.loadFailed";
    default:
      if (scope === "profile") return "profile.errors.loadFailed";
      if (listingsScope) return "listings.manage.errors.loadFailed";
      if (scope === "onboarding") return "onboarding.errors.loadFailed";
      if (scope === "analytics") return "analytics.errors.loadFailed";
      return "home.errors.loadFailed";
  }
}
