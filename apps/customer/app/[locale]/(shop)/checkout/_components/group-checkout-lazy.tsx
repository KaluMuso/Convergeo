"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

import type { GroupCheckoutLabels } from "./group-checkout";

type GroupCheckoutProps = {
  locale: string;
  groupId: string | null;
  labels: GroupCheckoutLabels;
};

// The interactive group (ticket / service) checkout is only reached with
// ?group=…, so keep it out of the /checkout first-load JS budget (bundle-guard,
// CLAUDE.md #7).
const GroupCheckoutChunk = dynamic(
  () => import("./group-checkout").then((mod) => mod.GroupCheckout),
  { ssr: false },
);

/**
 * Static shell with the same markup/spacing as GroupCheckout's loading state, so
 * the LCP element (heading + status line) is in the server HTML and paints before
 * any client JS; the chunk then swaps in without layout shift.
 */
export function GroupCheckoutLazy(props: GroupCheckoutProps) {
  return (
    <Suspense
      fallback={
        <section className="space-y-4 px-4 py-6" data-testid="group-checkout" aria-busy="true">
          <h1 className="font-display text-h1 text-display-ink">{props.labels.pageTitle}</h1>
          <p className="font-body text-sm text-text-3" aria-live="polite">
            {props.labels.loading}
          </p>
        </section>
      }
    >
      <GroupCheckoutChunk {...props} />
    </Suspense>
  );
}
