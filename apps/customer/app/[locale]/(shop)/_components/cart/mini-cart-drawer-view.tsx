"use client";

import { formatK } from "@vergeo/i18n";
import { BottomSheet } from "@vergeo/ui/src/bottom-sheet";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useReducer } from "react";

import { initializeCustomerSession } from "../../../../../lib/customer-session";
import { formatListingQuantity, formatMadeToOrderLeadTime } from "../sale-quantity";

import { CartEmptyTrustList } from "./cart-empty-trust-list";
import { getCartItemCount, subscribeStore, useCartStore } from "./cart-store";
import {
  markIdentityBarrier,
  refreshCart,
  useCartActions,
  type MiniCartLabels,
} from "./mini-cart-drawer";
import { VariantLineLabel } from "./variant-line-label";

import { cartLineTitle } from "@/lib/cart-line-title";

function EmptyCartIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5.5 6.5h13l-1.1 7.15a2 2 0 0 1-1.98 1.7H8.17a2 2 0 0 1-1.96-1.6L4.8 3.95H3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M9.2 19.25h.01M16 19.25h.01"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2.5"
      />
      <path d="m9 10.8 1.9 1.9 4.2-4.4" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function MiniCartEmptyState({
  locale,
  labels,
  onBrowse,
}: {
  locale: string;
  labels: Pick<MiniCartLabels, "emptyTitle" | "emptyBody" | "browseCta" | "emptyTrust">;
  onBrowse?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 p-6 text-center" data-testid="mini-cart-empty">
      <div className="text-text-3">
        <EmptyCartIcon />
      </div>
      <div className="flex max-w-sm flex-col gap-2">
        <p className="font-display text-xl text-display-ink">{labels.emptyTitle}</p>
        <p className="text-sm text-text-2">{labels.emptyBody}</p>
      </div>
      <LinkButton href={`/${locale}`} variant="secondary" onClick={onBrowse} LinkComponent={Link}>
        {labels.browseCta}
      </LinkButton>
      <CartEmptyTrustList labels={labels.emptyTrust} compact />
    </div>
  );
}

type MiniCartDrawerProps = {
  locale: string;
  labels: MiniCartLabels;
};

export function MiniCartDrawer({ locale, labels }: MiniCartDrawerProps) {
  const { cart, drawerOpen, lastAddedMessage, loadError, loading } = useCartStore();
  const { closeDrawer, refresh } = useCartActions();
  // See CartPageView: `cart.itemCount` is an ICU plural, so it is formatted here
  // rather than interpolated from a template label.
  const tCheckout = useTranslations("checkout");
  const count = getCartItemCount(cart);

  useEffect(() => {
    void refreshCart();
  }, []);

  return (
    <>
      <p className="sr-only" aria-live="polite" aria-atomic="true" data-testid="mini-cart-live">
        {lastAddedMessage ?? ""}
      </p>
      <BottomSheet
        open={drawerOpen}
        onClose={closeDrawer}
        title={labels.title}
        data-testid="mini-cart-drawer"
        snapHeight="70vh"
      >
        <div className="mb-2 flex justify-end">
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-sm px-3 text-sm font-medium text-text-2 transition-colors hover:bg-bg-2 hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing motion-reduce:transition-none"
            aria-label={labels.close}
            data-testid="mini-cart-close"
            onClick={closeDrawer}
          >
            {labels.close}
          </button>
        </div>
        {loadError && !cart ? (
          <div className="flex flex-col gap-3 p-4" data-testid="mini-cart-load-error" role="alert">
            <p className="font-display text-lg font-semibold text-text">{labels.loadErrorTitle}</p>
            <p className="text-sm text-text-2">{labels.loadErrorBody}</p>
            <button
              type="button"
              className="inline-flex min-h-11 w-full items-center justify-center rounded-sm bg-primary px-4 text-sm font-medium text-surface transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing motion-reduce:transition-none disabled:opacity-60"
              data-testid="mini-cart-load-error-retry"
              disabled={loading}
              onClick={() => {
                void refresh();
              }}
            >
              {labels.loadErrorRetry}
            </button>
          </div>
        ) : cart && count > 0 ? (
          <div className="flex flex-col gap-4 p-4">
            <p className="text-sm text-text-2" data-testid="mini-cart-count" aria-live="polite">
              {tCheckout("cart.itemCount", { count })}
            </p>
            <ul className="flex flex-col gap-3">
              {cart.items.map((item) => {
                const leadTimeLabel = formatMadeToOrderLeadTime(
                  item.fulfilment_mode,
                  item.lead_time_days,
                  labels.madeToOrderLeadTime,
                  labels.leadTimeWhen,
                );

                return (
                  <li key={item.id} className="flex items-start justify-between gap-3 text-sm">
                    <span className="min-w-0 text-text">
                      <span className="block truncate">
                        {cartLineTitle(item, tCheckout("cart.untitledItem"))}
                      </span>
                      <VariantLineLabel
                        options={item.variant_options}
                        template={tCheckout.raw("variant.option") as string}
                        separator={tCheckout.raw("variant.separator") as string}
                        testId={`mini-cart-variant-${item.listing_id}`}
                      />
                      <span className="block text-xs text-text-2">
                        {labels.quantityValue.replace(
                          "{count}",
                          formatListingQuantity(
                            item.qty,
                            item.sale_unit,
                            item.unit_step_milli,
                            locale,
                            labels.saleUnits,
                          ),
                        )}
                      </span>
                      {leadTimeLabel ? (
                        <span
                          className="block text-xs font-medium text-text-2"
                          data-testid={`mini-cart-lead-time-${item.listing_id}`}
                        >
                          {leadTimeLabel}
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 font-mono text-text">
                      {formatK(item.line_total_ngwee)}
                    </span>
                  </li>
                );
              })}
            </ul>
            <div className="flex items-center justify-between border-t border-border pt-3">
              <span className="font-medium text-text">{labels.subtotal}</span>
              <span className="font-mono font-semibold text-text" data-testid="mini-cart-subtotal">
                {formatK(cart.subtotal_ngwee)}
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <LinkButton
                href={`/${locale}/checkout`}
                variant="primary"
                size="lg"
                className="w-full min-h-11"
                onClick={closeDrawer}
                LinkComponent={Link}
              >
                {labels.checkoutCta}
              </LinkButton>
              <LinkButton
                href={`/${locale}/cart`}
                variant="secondary"
                className="w-full min-h-11"
                onClick={closeDrawer}
                LinkComponent={Link}
              >
                {labels.viewCart}
              </LinkButton>
            </div>
          </div>
        ) : (
          <MiniCartEmptyState locale={locale} labels={labels} onBrowse={closeDrawer} />
        )}
      </BottomSheet>
    </>
  );
}

export function CartHost({ locale, labels }: MiniCartDrawerProps) {
  const [, bump] = useReducer((value: number) => value + 1, 0);
  // Set during render so the drawer's first refresh already waits for the
  // reconciled customer session (child effects run before this host's).
  markIdentityBarrier();

  useEffect(() => {
    void initializeCustomerSession().catch(() => undefined);
  }, []);

  useEffect(() => {
    return subscribeStore(() => bump());
  }, []);

  return <MiniCartDrawer locale={locale} labels={labels} />;
}
