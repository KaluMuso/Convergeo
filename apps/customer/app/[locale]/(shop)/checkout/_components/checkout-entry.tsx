"use client";

import { Skeleton } from "@vergeo/ui/src/skeleton";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { resolveGroupParam, type SearchParams } from "../_lib/group-checkout";

import { GroupCheckoutLazy } from "./group-checkout-lazy";
import { CheckoutShell } from "./step-fulfilment";

import type { GroupCheckoutLabels } from "./group-checkout";
import type { CheckoutShellLabels } from "./step-fulfilment";

type Props = {
  locale: string;
  labels: CheckoutShellLabels;
  groupLabels: GroupCheckoutLabels;
};

function Switch({ locale, labels, groupLabels }: Props) {
  const params = useSearchParams();
  const query: SearchParams = {};
  for (const key of new Set(params.keys())) {
    const all = params.getAll(key);
    query[key] = all.length > 1 ? all : all[0];
  }
  const groupId = resolveGroupParam(query);
  if (groupId !== undefined) {
    return <GroupCheckoutLazy locale={locale} groupId={groupId} labels={groupLabels} />;
  }
  return <CheckoutShell locale={locale} labels={labels} />;
}

/**
 * Static, effect-free placeholder: same heading + contact subtitle (the LCP
 * text of the cart checkout) plus inert skeletons. It must NOT mount
 * CheckoutShell, whose effects create a product checkout session — that must
 * never run for a ?group= handoff.
 */
function EntrySkeleton({ labels }: { labels: CheckoutShellLabels }) {
  return (
    <div className="space-y-6" aria-busy="true" data-testid="checkout-entry-skeleton">
      <h1 className="font-display text-h1 text-display-ink">{labels.pageTitle}</h1>
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="font-display text-h2 text-display-ink">{labels.contact.title}</h2>
          <p className="font-body text-sm text-text-2">{labels.contact.subtitle}</p>
        </div>
        <div className="flex flex-col gap-4" aria-hidden="true">
          <div className="space-y-2">
            <Skeleton shape="line" width="8rem" />
            <div className="flex gap-2">
              <Skeleton width="6rem" height="3rem" />
              <Skeleton className="min-w-0 flex-1" height="3rem" />
            </div>
            <Skeleton shape="line" width="70%" />
          </div>
          <Skeleton height="3rem" />
        </div>
      </div>
    </div>
  );
}

/**
 * Reads ?group= on the client so the /checkout page itself stays statically
 * prerendered (reading searchParams on the server made the route dynamic and
 * regressed LCP). The Suspense fallback is the static skeleton, so the cart shell
 * only mounts once we know there is no group.
 */
export function CheckoutEntry(props: Props) {
  return (
    <Suspense fallback={<EntrySkeleton labels={props.labels} />}>
      <Switch {...props} />
    </Suspense>
  );
}
