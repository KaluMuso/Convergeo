import { createServerClient } from "@vergeo/auth/server-client";
import { cookies } from "next/headers";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

export type ProductCartSnapshot = {
  itemCount: number;
  ticketCount: number;
};

function readLineCount(payload: unknown, key: string): number {
  if (!payload || typeof payload !== "object") {
    return 0;
  }
  const value = (payload as Record<string, unknown>)[key];
  return Array.isArray(value) ? value.length : 0;
}

/** True when the buyer has nothing left to check out (products or tickets). */
export function isProductCartEmpty(snapshot: ProductCartSnapshot): boolean {
  return snapshot.itemCount === 0 && snapshot.ticketCount === 0;
}

/**
 * Best-effort server read of the buyer's product cart before mounting checkout.
 * Returns `null` when the API is unreachable so the client guard can decide.
 */
export async function readProductCartSnapshot(): Promise<ProductCartSnapshot | null> {
  const url = absoluteApiUrl("/cart");
  if (!url) {
    return null;
  }

  const cookieStore = await cookies();
  const headers = new Headers({ Accept: "application/json" });

  try {
    const supabase = createServerClient(cookieStore);
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      headers.set("Authorization", `Bearer ${session.access_token}`);
    }
  } catch {
    // Guest checkout still forwards cookies below.
  }

  const cookieHeader = cookieStore
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
  if (cookieHeader) {
    headers.set("Cookie", cookieHeader);
  }

  try {
    const response = await fetch(url, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) {
      return null;
    }
    const payload: unknown = await response.json();
    return {
      itemCount: readLineCount(payload, "items"),
      ticketCount: readLineCount(payload, "ticket_lines"),
    };
  } catch {
    return null;
  }
}
