"use client";

import dynamic from "next/dynamic";

import type { GroupCheckoutLabels } from "./group-checkout";

type GroupCheckoutProps = {
  locale: string;
  groupId: string | null;
  labels: GroupCheckoutLabels;
};

// The group (ticket / service) checkout is only reached with ?group=…, so keep
// it out of the /checkout first-load JS budget (bundle-guard, CLAUDE.md #7).
const GroupCheckoutChunk = dynamic(
  () => import("./group-checkout").then((mod) => mod.GroupCheckout),
  { ssr: false },
);

export function GroupCheckoutLazy(props: GroupCheckoutProps) {
  return <GroupCheckoutChunk {...props} />;
}
