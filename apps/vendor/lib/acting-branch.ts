import { setApiDefaultHeaders } from "@vergeo/config";

/**
 * Multi-branch: the shop an owner is working on. Stored in a first-party cookie
 * and sent to the API as `X-Vendor-Branch` on every request; the API only uses
 * it to NARROW lookups already scoped to the signed-in owner. Until a shop is
 * picked the value is `primary` (the business's main shop), so an owner with
 * several shops never gets an ambiguous answer.
 */
export const ACTING_BRANCH_COOKIE = "cv_branch";
export const ACTING_BRANCH_HEADER = "X-Vendor-Branch";
export const PRIMARY_BRANCH = "primary";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ONE_YEAR_S = 60 * 60 * 24 * 365;

export function isBranchId(value: string | null | undefined): value is string {
  return typeof value === "string" && UUID_RE.test(value);
}

/** Acting branch from a `document.cookie` string; `primary` when unset or malformed. */
export function readActingBranch(cookieString: string | null | undefined): string {
  if (!cookieString) return PRIMARY_BRANCH;
  for (const part of cookieString.split(";")) {
    const [rawName, ...rest] = part.trim().split("=");
    if (rawName === ACTING_BRANCH_COOKIE) {
      const value = decodeURIComponent(rest.join("="));
      return isBranchId(value) ? value.toLowerCase() : PRIMARY_BRANCH;
    }
  }
  return PRIMARY_BRANCH;
}

export function serializeActingBranchCookie(branchId: string | null, secure: boolean): string {
  const value = branchId && isBranchId(branchId) ? branchId.toLowerCase() : "";
  const maxAge = value ? ONE_YEAR_S : 0;
  return `${ACTING_BRANCH_COOKIE}=${value}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure ? "; Secure" : ""}`;
}

export function writeActingBranch(branchId: string | null): void {
  if (typeof document === "undefined") return;
  const secure = typeof location !== "undefined" && location.protocol === "https:";
  document.cookie = serializeActingBranchCookie(branchId, secure);
}

export function actingBranchHeaders(): Record<string, string> {
  if (typeof document === "undefined") return {};
  return { [ACTING_BRANCH_HEADER]: readActingBranch(document.cookie) };
}

let installed = false;

/** Register the header on every `createApiClient` request (idempotent, browser only). */
export function installActingBranchHeader(): void {
  if (installed || typeof document === "undefined") return;
  installed = true;
  setApiDefaultHeaders(actingBranchHeaders);
}
