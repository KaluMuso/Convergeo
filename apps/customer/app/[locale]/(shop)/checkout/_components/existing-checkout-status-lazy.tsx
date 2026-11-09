"use client";

import dynamic from "next/dynamic";

import type { ExistingCheckoutStatusProps } from "./existing-checkout-status";

// Only ?session=/?group= handoffs render this; keep it off /checkout first-load JS.
const ExistingCheckoutStatusChunk = dynamic(
  () => import("./existing-checkout-status").then((mod) => mod.ExistingCheckoutStatus),
  { ssr: false },
);

export function ExistingCheckoutStatus(props: ExistingCheckoutStatusProps) {
  return <ExistingCheckoutStatusChunk {...props} />;
}
