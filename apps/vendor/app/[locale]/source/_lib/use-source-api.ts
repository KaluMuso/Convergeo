"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { useMemo, useRef } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";

/** API client bound to the signed-in vendor's token; `ready` once a session exists. */
export function useSourceApi() {
  const { session } = useSession();
  const token = session?.access_token ?? null;
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;
  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => tokenRef.current,
      }),
    [],
  );
  return { client, ready: token !== null };
}

type ApiError = { details?: { message_key?: string } };

/** Stable vendor.source error key (relative) for an API failure. */
export function sourceErrorKey(error: unknown): string {
  const key = (error as ApiError | null)?.details?.message_key;
  if (key === "vendor.sourcing.errors.rateLimited") return "errors.rateLimited";
  if (key === "vendor.sourcing.errors.importRateLimited") return "errors.importRateLimited";
  if (key === "vendor.sourcing.errors.prohibited") return "errors.prohibited";
  return "errors.generic";
}
