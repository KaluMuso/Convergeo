import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { CartPageView, type CartPageLabels } from "../_components/cart/vendor-groups";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type CartPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function CartPage({ params }: CartPageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  const baseMessages = await getMessages();
  const checkoutMessages = await loadNamespace(locale as Locale, "checkout");
  const messages = { ...baseMessages, checkout: checkoutMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "checkout" });

  const labels: CartPageLabels = {
    title: t("cart.title"),
    emptyTitle: t("cart.emptyTitle"),
    emptyBody: t("cart.emptyBody"),
    emptyTrust: {
      escrow: t("cart.emptyTrustEscrow"),
      delivery: t("cart.emptyTrustDelivery"),
      pickup: t("cart.emptyTrustPickup"),
    },
    browseCta: t("cart.browseCta"),
    itemCount: t("cart.itemCount"),
    subtotal: t("cart.subtotal"),
    total: t("cart.total"),
    checkoutCta: t("cart.checkoutCta"),
    updateError: t("cart.updateError"),
    vendor: {
      vendorGroup: t("cart.vendorGroup"),
      vendorSubtotal: t("cart.vendorSubtotal"),
      deliveryEligible: t("cart.deliveryEligible"),
      deliveryHint: t("cart.deliveryHint"),
      deliveryThreshold: t("cart.deliveryThreshold"),
      deliveryScopeNote: t("cart.deliveryScopeNote"),
      freeDeliveryProgress: t("cart.freeDeliveryProgress"),
      freeDeliveryUnlocked: t("cart.freeDeliveryUnlocked"),
    },
    line: {
      decrease: t("cart.qtyDecrease"),
      increase: t("cart.qtyIncrease"),
      value: t("cart.qtyValue"),
      updating: t("cart.updating"),
      decreaseSymbol: t("cart.qtyDecreaseSymbol"),
      increaseSymbol: t("cart.qtyIncreaseSymbol"),
      unitPrice: t("cart.unitPrice"),
      lineTotal: t("cart.lineTotal"),
      remove: t("cart.remove"),
      removeLabel: t("cart.removeLabel"),
      outOfStockLine: t("cart.outOfStockLine"),
    },
    notices: {
      title: t("cart.noticesTitle"),
      priceChanged: t("cart.noticePriceChanged"),
      outOfStock: t("cart.noticeOutOfStock"),
      qtyReduced: t("cart.noticeQtyReduced"),
    },
    miniCart: {
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
    },
  };

  return (
    <div className="lg:mx-auto lg:w-full lg:max-w-2xl">
      <CartPageView locale={locale} labels={labels} />
    </div>
  );
}
