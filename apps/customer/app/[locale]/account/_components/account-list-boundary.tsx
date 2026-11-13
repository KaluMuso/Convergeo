"use client";

import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { useSession } from "../../../../lib/customer-session";

/** Hide an already-mounted server list as soon as its authenticated identity changes. */
export function AccountListBoundary({
  accountId,
  children,
}: {
  accountId: string;
  children: ReactNode;
}) {
  const { session, loading, generation } = useSession();
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);
  const refreshedGeneration = useRef<number | null>(null);

  // A stale RSC payload can mount after an account change. Recheck before its
  // first browser paint, including when this boundary has never mounted before.
  useLayoutEffect(() => setHydrated(true), []);

  const matches = !loading && session?.user.id === accountId;
  useEffect(() => {
    if (!hydrated || loading || matches || refreshedGeneration.current === generation) return;
    refreshedGeneration.current = generation;
    router.refresh();
  }, [generation, hydrated, loading, matches, router]);

  // Keep the authenticated server HTML for SSR. After hydration, only the
  // matching browser identity may see this server payload or its action links.
  return !hydrated || matches ? children : null;
}
