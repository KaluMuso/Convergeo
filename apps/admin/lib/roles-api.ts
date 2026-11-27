"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { ApiError, createApiClient } from "@vergeo/config";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { getApiBaseUrl } from "./api-base-url";

export const rolesApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type AdminPermissions = {
  /** The signed-in operator; used only to hide self-deactivation in the UI. */
  user_id?: string;
  permissions: string[];
  can_manage_roles: boolean;
  unrestricted: boolean;
};

export type AdminRole = { key: string; name: string; permissions: string[] };
export type AdminRoleAssignment = {
  user_id: string;
  role: string;
  display_name?: string | null;
  email?: string | null;
};

export type AccountMatch = {
  user_id: string;
  display_name: string | null;
  email: string | null;
  roles: string[];
};

/** Name, then email, then a short id — never a bare full UUID. */
export function accountLabel(account: {
  user_id: string;
  display_name?: string | null;
  email?: string | null;
}): string {
  return account.display_name || account.email || `…${account.user_id.slice(-6)}`;
}

export async function lookupAccounts(query: string): Promise<AccountMatch[]> {
  const result = await rolesApi.request<{ accounts: AccountMatch[] }>(
    `/admin/accounts/lookup?${new URLSearchParams({ q: query }).toString()}`,
    { cache: "no-store" },
  );
  return Array.isArray(result?.accounts) ? result.accounts : [];
}

const PERMISSIONS = new Set([
  "finance.read",
  "finance.operate",
  "events.manage",
  "products.manage",
  "services.read",
  "services.manage",
  "vendors.manage",
  "ads.manage",
  "analytics.read",
  "inventory.read",
  "support.manage",
  "logistics.manage",
  "cod.reconcile",
  "audit.read",
]);

export async function loadAdminPermissions(): Promise<AdminPermissions> {
  const value = await rolesApi.request<AdminPermissions>("/admin/me/permissions", {
    cache: "no-store",
  });
  if (
    !value ||
    !Array.isArray(value.permissions) ||
    !value.permissions.every(
      (permission) => typeof permission === "string" && PERMISSIONS.has(permission),
    ) ||
    typeof value.unrestricted !== "boolean" ||
    typeof value.can_manage_roles !== "boolean"
  ) {
    throw new Error("Invalid admin permissions response");
  }
  return value;
}

// Presentation only. The API remains authoritative for every privileged request.
export const AdminPermissionsContext = createContext<AdminPermissions | null>(null);
export const AdminPermissionRefreshContext = createContext<(() => void) | null>(null);

export function useAdminPermissions(): AdminPermissions | null {
  return useContext(AdminPermissionsContext);
}

export function useRefreshAdminPermissions() {
  return useContext(AdminPermissionRefreshContext);
}

type PermissionCheck = {
  route: string | null;
  grants: AdminPermissions | null;
  error: boolean;
};

/**
 * How long the last confirmed grants may paint the next route while a background
 * recheck runs. Presentation only: every privileged API request reloads current
 * database roles, so a stale paint can never authorise an action or expose data.
 */
export const ADMIN_GRANTS_REUSE_MS = 120_000;

function sameGrants(a: AdminPermissions | null, b: AdminPermissions): boolean {
  if (!a) return false;
  return (
    a.user_id === b.user_id &&
    a.unrestricted === b.unrestricted &&
    a.can_manage_roles === b.can_manage_roles &&
    a.permissions.length === b.permissions.length &&
    [...a.permissions].sort().join("|") === [...b.permissions].sort().join("|")
  );
}

/** A real answer from the API about the caller (401/403, malformed grants), not a transport blip. */
function isDefinitiveFailure(error: unknown): boolean {
  if (error instanceof ApiError) return error.status !== 0 && error.status < 500;
  return true;
}

export function useAdminPermissionCheck(route: string | null) {
  const [check, setCheck] = useState<PermissionCheck>({
    route: null,
    grants: null,
    error: false,
  });
  // Last grants the API confirmed for this signed-in account. Lets a route change keep
  // painting while the recheck runs, instead of making every navigation wait one extra
  // `/admin/me/permissions` round trip before the new page can even start its own fetch.
  const confirmedRef = useRef<{ grants: AdminPermissions; at: number } | null>(null);
  const checkRef = useRef(check);
  checkRef.current = check;
  const refreshRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => refreshRef.current(), []);

  useEffect(() => {
    if (route === null) {
      confirmedRef.current = null;
      setCheck({ route: null, grants: null, error: false });
      return;
    }
    let active = true;
    let request = 0;
    let unsubscribe: (() => void) | undefined;
    let authTimer: number | undefined;

    // "hard": drop the grants first (initial load, explicit refresh after a role
    // mutation, account switch). "soft": used only when moving to another route within the
    // same session; keep painting the last confirmed grants while rechecking, and let a
    // definitive failure or a changed grant set win.
    function reload(mode: "hard" | "soft" | "quiet" = "hard") {
      if (!active) return;
      const current = ++request;
      // "quiet": refocus. The mounted page (and any form state in it) stays exactly as it is
      // while the recheck runs, whatever the age of the last confirmation.
      const quiet =
        mode === "quiet" &&
        checkRef.current.route === route &&
        checkRef.current.grants !== null &&
        !checkRef.current.error;
      const reusable =
        mode === "soft" &&
        confirmedRef.current !== null &&
        Date.now() - confirmedRef.current.at < ADMIN_GRANTS_REUSE_MS
          ? confirmedRef.current.grants
          : null;
      if (quiet) {
        // Nothing to repaint: keep the current grants until the answer arrives.
      } else if (reusable) {
        setCheck((previous) =>
          previous.route === route && previous.grants && !previous.error
            ? previous
            : { route, grants: reusable, error: false },
        );
      } else {
        confirmedRef.current = null;
        setCheck({ route, grants: null, error: false });
      }
      void loadAdminPermissions().then(
        (grants) => {
          if (!active || current !== request) return;
          const previous = confirmedRef.current?.grants ?? null;
          const next = sameGrants(previous, grants) ? (previous as AdminPermissions) : grants;
          confirmedRef.current = { grants: next, at: Date.now() };
          setCheck({ route, grants: next, error: false });
        },
        (error: unknown) => {
          if (!active || current !== request) return;
          if ((reusable || quiet) && !isDefinitiveFailure(error)) return;
          confirmedRef.current = null;
          setCheck({ route, grants: null, error: true });
        },
      );
    }

    // Refocus rechecks quietly: the page stays mounted (in-progress forms survive an
    // alt-tab). It is removed only if the answer shrinks the grants or is a 401/403.
    function onFocus() {
      reload("quiet");
    }

    function onVisibility() {
      if (document.visibilityState === "visible") reload("quiet");
    }

    refreshRef.current = () => reload("hard");
    reload("soft");
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    void getBrowserClient().then(
      (client) => {
        if (!active) return;
        const {
          data: { subscription },
        } = client.auth.onAuthStateChange(() => {
          if (!active) return;
          // Clear old-account grants immediately. Defer auth reads until the
          // Supabase callback releases its session lock.
          ++request;
          confirmedRef.current = null;
          setCheck({ route, grants: null, error: false });
          window.clearTimeout(authTimer);
          authTimer = window.setTimeout(() => reload("hard"), 0);
        });
        unsubscribe = () => subscription.unsubscribe();
      },
      () => {
        if (active) {
          ++request;
          confirmedRef.current = null;
          setCheck({ route, grants: null, error: true });
        }
      },
    );

    return () => {
      active = false;
      refreshRef.current = () => {};
      window.clearTimeout(authTimer);
      unsubscribe?.();
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [route]);

  if (check.route === route) {
    return { ...check, refresh };
  }
  // Reject a previous route's snapshot before effects run on navigation, but paint the
  // account's recently confirmed grants so the new page mounts (and fetches) at once.
  const confirmed = confirmedRef.current;
  const reusable =
    route !== null && confirmed !== null && Date.now() - confirmed.at < ADMIN_GRANTS_REUSE_MS
      ? confirmed.grants
      : null;
  return { route, grants: reusable, error: false, refresh };
}
