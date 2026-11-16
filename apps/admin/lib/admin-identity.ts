"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { useEffect, useState } from "react";

import type { AdminPermissions } from "./roles-api";

/** Which role label the top bar shows. Custom roles carry no key in the grants payload. */
export type AdminRoleKind = "superadmin" | "admin" | "custom";

export type AdminIdentity = {
  email: string | null;
  name: string | null;
};

const EMPTY_IDENTITY: AdminIdentity = { email: null, name: null };

/**
 * Presentation only: the API stays authoritative for every privileged request.
 * `can_manage_roles` is true only for superadmin; `unrestricted` for admin and superadmin.
 */
export function resolveAdminRoleKind(
  grants: Pick<AdminPermissions, "unrestricted" | "can_manage_roles"> | null,
): AdminRoleKind | null {
  if (!grants) {
    return null;
  }
  if (grants.can_manage_roles) {
    return "superadmin";
  }
  if (grants.unrestricted) {
    return "admin";
  }
  return "custom";
}

function clean(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

type SessionUserLike = {
  email?: unknown;
  user_metadata?: Record<string, unknown> | null;
} | null;

export function readAdminIdentity(user: SessionUserLike | undefined): AdminIdentity {
  if (!user) {
    return EMPTY_IDENTITY;
  }
  const meta = user.user_metadata ?? {};
  return {
    email: clean(user.email),
    name: clean(meta.full_name) ?? clean(meta.name) ?? clean(meta.display_name),
  };
}

/** Name for the top bar: profile name, else the email local part, else null. */
export function adminDisplayName(identity: AdminIdentity): string | null {
  if (identity.name) {
    return identity.name;
  }
  if (identity.email) {
    return identity.email.split("@")[0] || identity.email;
  }
  return null;
}

/**
 * Reads the signed-in admin's name and email from the local Supabase session (no extra
 * API call). `reloadKey` changes when permissions reload, which also covers account switches.
 */
export function useAdminIdentity(enabled: boolean, reloadKey: unknown): AdminIdentity {
  const [identity, setIdentity] = useState<AdminIdentity>(EMPTY_IDENTITY);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let active = true;
    void (async () => {
      try {
        const client = await getBrowserClient();
        const { data } = await client.auth.getSession();
        if (active) {
          setIdentity(readAdminIdentity(data?.session?.user));
        }
      } catch {
        // Identity is cosmetic; the shell works without it.
      }
    })();
    return () => {
      active = false;
    };
  }, [enabled, reloadKey]);

  return identity;
}
