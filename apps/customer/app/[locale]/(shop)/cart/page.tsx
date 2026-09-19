import { loadNamespace, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { Suspense } from "react";

import { CartPageSkeleton } from "../_components/cart/cart-page-skeleton";
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
  // Labels cross the server→client boundary as serializable strings, so messages
  // that still carry `{…}` placeholders must be read with `t.raw` — `t()` cannot
  // format them without values and falls back to the bare key path
  // (see the same pattern in the auth OTP page).
  const raw = (key: string) => String(t.raw(key));

  const labels: CartPageLabels = {
    title: t("cart.title"),
    loading: t("cart.loading"),
    emptyTitle: t("cart.emptyTitle"),
    emptyBody: t("cart.emptyBody"),
    emptyTrust: {
      escrow: t("cart.emptyTrustEscrow"),
      delivery: t("cart.emptyTrustDelivery"),
      pickup: t("cart.emptyTrustPickup"),
    },
    browseCta: t("cart.browseCta"),
    subtotal: t("cart.subtotal"),
    total: t("cart.total"),
    checkoutCta: t("cart.checkoutCta"),
    updateError: t("cart.updateError"),
    loadErrorTitle: t("cart.loadErrorTitle"),
    loadErrorBody: t("cart.loadErrorBody"),
    loadErrorRetry: t("cart.loadErrorRetry"),
    multiSellerNote: t("cart.multiSellerNote"),
    escrowTeaser: t("cart.escrowTeaser"),
    escrowSteps: [
      t("checkout.review.escrowStep1"),
      t("checkout.review.escrowStep2"),
      t("checkout.review.escrowStep3"),
    ],
    stockUnavailableNotice: t("cart.stockUnavailableNotice"),
    summaryHeading: t("cart.summaryHeading"),
    vendor: {
      vendorGroup: t("cart.vendorGroup"),
      vendorSubtotal: raw("cart.vendorSubtotal"),
      deliveryEligible: t("cart.deliveryEligible"),
      deliveryHint: raw("cart.deliveryHint"),
      deliveryThreshold: raw("cart.deliveryThreshold"),
      deliveryScopeNote: t("cart.deliveryScopeNote"),
      freeDeliveryProgress: raw("cart.freeDeliveryProgress"),
      freeDeliveryUnlocked: t("cart.freeDeliveryUnlocked"),
      sellerIndex: raw("cart.sellerIndex"),
    },
    line: {
      decrease: t("cart.qtyDecrease"),
      increase: t("cart.qtyIncrease"),
      value: raw("cart.qtyValue"),
      updating: t("cart.updating"),
      decreaseSymbol: t("cart.qtyDecreaseSymbol"),
      increaseSymbol: t("cart.qtyIncreaseSymbol"),
      unitPrice: raw("cart.unitPrice"),
      unitPriceMeasured: raw("cart.unitPriceMeasured"),
      saleUnits: {
        each: t("cart.saleUnits.each"),
        metre: t("cart.saleUnits.metre"),
        kg: t("cart.saleUnits.kg"),
        litre: t("cart.saleUnits.litre"),
        bag: t("cart.saleUnits.bag"),
        sqm: t("cart.saleUnits.sqm"),
      },
      madeToOrderLeadTime: raw("cart.madeToOrderLeadTime"),
      lineTotal: raw("cart.lineTotal"),
      quotedPriceBadge: t("cart.quotedPriceBadge"),
      remove: t("cart.remove"),
      removeLabel: raw("cart.removeLabel"),
      saveForLater: t("cart.saveForLater"),
      saveForLaterLabel: raw("cart.saveForLaterLabel"),
      outOfStockLine: t("cart.outOfStockLine"),
    },
    notices: {
      title: t("cart.noticesTitle"),
      priceChanged: raw("cart.noticePriceChanged"),
      outOfStock: t("cart.noticeOutOfStock"),
      qtyReduced: raw("cart.noticeQtyReduced"),
    },
    miniCart: {
      title: t("cart.miniCartTitle"),
      close: t("cart.miniCartClose"),
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
      quantityValue: raw("cart.qtyValue"),
      saleUnits: {
        each: t("cart.saleUnits.each"),
        metre: t("cart.saleUnits.metre"),
        kg: t("cart.saleUnits.kg"),
        litre: t("cart.saleUnits.litre"),
        bag: t("cart.saleUnits.bag"),
        sqm: t("cart.saleUnits.sqm"),
      },
      madeToOrderLeadTime: raw("cart.madeToOrderLeadTime"),
    },
  };

  return (
    <div className="mx-auto w-full max-w-lg px-4 py-6 lg:max-w-5xl">
      <Suspense fallback={<CartPageSkeleton loadingLabel={labels.loading} />}>
        <CartPageView locale={locale} labels={labels} />
      </Suspense>
    </div>
  );
}
