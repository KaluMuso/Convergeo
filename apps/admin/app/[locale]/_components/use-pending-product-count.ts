"use client";

import { useCallback, useEffect, useState } from "react";

import { type AdminPermissions, useAdminPermissions } from "../../../lib/roles-api";
import { listPendingCanonicalProducts } from "../moderation/products/_components/api";

/** Pass `grants` from the shell when the sidebar is outside the permissions context. */
export function usePendingProductModerationCount(
  grantsOverride?: AdminPermissions | null,
): number | null {
  const fromContext = useAdminPermissions();
  const grants = grantsOverride === undefined ? fromContext : grantsOverride;
  const allowed =
    !!grants && (grants.unrestricted || grants.permissions.includes("products.manage"));
  const [count, setCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!allowed) {
      setCount(null);
      return;
    }
    try {
      const items = await listPendingCanonicalProducts();
      setCount(items.length);
    } catch {
      setCount(null);
    }
  }, [allowed]);

  useEffect(() => {
    void load();
  }, [load]);

  return count;
}
