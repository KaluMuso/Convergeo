import type { BuyAgainLabels } from "./buy-again";

type Translate = (key: string, values?: Record<string, string | number>) => string;
type RawTranslate = { raw(key: string): unknown };

/** Builds the buy-again labels from the `orders` namespace (templates kept raw). */
export function buildBuyAgainLabels(t: Translate & RawTranslate): BuyAgainLabels {
  return {
    button: t("buyAgain.button"),
    loading: t("buyAgain.loading"),
    error: t("buyAgain.error"),
    rateLimited: t("buyAgain.rateLimited"),
    added: String(t.raw("buyAgain.added")),
    nothingAdded: t("buyAgain.nothingAdded"),
    skippedTitle: t("buyAgain.skippedTitle"),
    skippedReasons: {
      unavailable: t("buyAgain.skipped.unavailable"),
      out_of_stock: t("buyAgain.skipped.out_of_stock"),
      variant_unavailable: t("buyAgain.skipped.variant_unavailable"),
    },
    priceChangeTitle: t("buyAgain.priceChangeTitle"),
    priceChangeLine: String(t.raw("buyAgain.priceChangeLine")),
    goToCart: t("buyAgain.goToCart"),
  };
}
