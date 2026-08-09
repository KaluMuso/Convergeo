"use client";

import dynamic from "next/dynamic";

import type { MiniCartLabels } from "./mini-cart-drawer";

const CartHostSlot = dynamic(() => import("./cart-host-slot").then((mod) => mod.CartHostSlot), {
  ssr: false,
});

type LazyCartHostSlotProps = {
  locale: string;
  labels: MiniCartLabels;
};

/** Defer mini-cart host off the shop-layout critical path (LCP). */
export function LazyCartHostSlot(props: LazyCartHostSlotProps) {
  return <CartHostSlot {...props} />;
}
