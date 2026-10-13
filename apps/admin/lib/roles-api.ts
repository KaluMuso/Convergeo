"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { createApiClient } from "@vergeo/config";
import { createContext, useContext, useEffect, useState } from "react";

import { getApiBaseUrl } from "./api-base-url";

export const rolesApi = createApiClient({
  baseUrl: getApiBaseUrl(),
  getToken: getBrowserAccessToken,
});

export type AdminPermissions = {
  permissions: string[];
  can_manage_roles: boolean;
  unrestricted: boolean;
};

export type AdminRole = { key: string; name: string; permissions: string[] };
export type AdminRoleAssignment = { user_id: string; role: string };

const PERMISSIONS = new Set([
  "finance.read",
  "events.manage",
  "products.manage",
  "services.read",
  "vendors.manage",
  "ads.manage",
  "analytics.read",
  "inventory.read",
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

export function useAdminPermissions(): AdminPermissions | null {
  return useContext(AdminPermissionsContext);
}

type PermissionCheck = {
  route: string | null;
  grants: AdminPermissions | null;
  error: boolean;
};

export function useAdminPermissionCheck(route: string | null) {
  const [check, setCheck] = useState<PermissionCheck>({ route: null, grants: null, error: false });

  useEffect(() => {
    if (route === null) {
      setCheck({ route: null, grants: null, error: false });
      return;
    }
    let active = true;
    let request = 0;
    let unsubscribe: (() => void) | undefined;
    let authTimer: number | undefined;

    function reload() {
      if (!active) return;
      const current = ++request;
      setCheck({ route, grants: null, error: false });
      void loadAdminPermissions().then(
        (grants) => {
          if (active && current === request) setCheck({ route, grants, error: false });
        },
        () => {
          if (active && current === request) setCheck({ route, grants: null, error: true });
        },
      );
    }

    function onVisibility() {
      if (document.visibilityState === "visible") reload();
    }

    reload();
    window.addEventListener("focus", reload);
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
          setCheck({ route, grants: null, error: false });
          window.clearTimeout(authTimer);
          authTimer = window.setTimeout(reload, 0);
        });
        unsubscribe = () => subscription.unsubscribe();
      },
      () => {
        if (active) {
          ++request;
          setCheck({ route, grants: null, error: true });
        }
      },
    );

    return () => {
      active = false;
      window.clearTimeout(authTimer);
      unsubscribe?.();
      window.removeEventListener("focus", reload);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [route]);

  // Reject a previous route's snapshot before effects run on navigation.
  return check.route === route ? check : { route, grants: null, error: false };
}
