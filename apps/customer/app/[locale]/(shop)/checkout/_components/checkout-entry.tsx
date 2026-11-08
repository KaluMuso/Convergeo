"use client";

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
 * Reads ?group= on the client so the /checkout page itself stays statically
 * prerendered (reading searchParams on the server made the route dynamic and
 * regressed LCP). The Suspense fallback is the cart shell, which is what the
 * static HTML shows.
 */
export function CheckoutEntry(props: Props) {
  return (
    <Suspense fallback={<CheckoutShell locale={props.locale} labels={props.labels} />}>
      <Switch {...props} />
    </Suspense>
  );
}
