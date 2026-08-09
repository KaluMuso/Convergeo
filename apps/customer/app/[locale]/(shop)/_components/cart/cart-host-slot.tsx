"use client";

import { CartHost, type MiniCartLabels } from "./mini-cart-drawer";

type CartHostSlotProps = {
  locale: string;
  labels: MiniCartLabels;
};

/**
 * Shop-layout mount for the mini-cart drawer so `openMiniCart()` works after
 * add-to-cart on PDP/PLP (not only on the cart page).
 */
export function CartHostSlot({ locale, labels }: CartHostSlotProps) {
  return <CartHost locale={locale} labels={labels} />;
}
