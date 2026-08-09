"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";

const CartHostSlot = dynamic(() => import("./cart-host-slot").then((mod) => mod.CartHostSlot), {
  ssr: false,
});

type LazyCartHostSlotProps = {
  locale: string;
};

/**
 * Defer mini-cart host + checkout-cart copy off the shop-layout critical path.
 * Labels resolve client-side so the server layout does not load the checkout
 * namespace on every shop route (home/PLP/PDP/checkout LCP).
 */
export function LazyCartHostSlot({ locale }: LazyCartHostSlotProps) {
  const t = useTranslations("checkout");
  return (
    <CartHostSlot
      locale={locale}
      labels={{
        title: t("cart.miniCartTitle"),
        close: t("cart.miniCartClose"),
        itemCount: t("cart.itemCount"),
        subtotal: t("cart.subtotal"),
        total: t("cart.total"),
        viewCart: t("cart.viewCart"),
        checkoutCta: t("cart.checkoutCta"),
        emptyTitle: t("cart.emptyTitle"),
        emptyBody: t("cart.emptyBody"),
        emptyTrust: {
          escrow: t("cart.emptyTrustEscrow"),
          delivery: t("cart.emptyTrustDelivery"),
          pickup: t("cart.emptyTrustPickup"),
        },
        browseCta: t("cart.browseCta"),
        openCart: t("cart.openCart"),
        loadErrorTitle: t("cart.loadErrorTitle"),
        loadErrorBody: t("cart.loadErrorBody"),
        loadErrorRetry: t("cart.loadErrorRetry"),
      }}
    />
  );
}
