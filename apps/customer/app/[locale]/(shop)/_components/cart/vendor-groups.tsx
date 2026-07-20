"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ChangeNotices, type ChangeNoticeLabels } from "./change-notices";
import { CartLineItem, type CartLineItemLabels } from "./line-items";
import {
  FREE_DELIVERY_THRESHOLD_NGEWEE,
  type ChangeNotice,
  type CartEmptyTrustLabels,
  type VendorGroup,
  CartEmptyTrustList,
  CartHost,
  CartProvider,
  getCartItemCount,
  useCartActions,
  useCartStore,
  type MiniCartLabels,
} from "./mini-cart-drawer";

export type VendorGroupLabels = {
  vendorGroup: string;
  vendorSubtotal: string;
  deliveryEligible: string;
  deliveryHint: string;
  deliveryThreshold: string;
  deliveryScopeNote: string;
  freeDeliveryProgress: string;
  freeDeliveryUnlocked: string;
};

type VendorGroupsProps = {
  groups: VendorGroup[];
  noticesByListingId: Record<string, ChangeNotice>;
  labels: VendorGroupLabels;
  lineLabels: CartLineItemLabels;
  onQtyChange: (listingId: string, qty: number) => Promise<void>;
  onRemove: (listingId: string) => Promise<void>;
};

function deliveryProgress(subtotalNgwee: number): number {
  return Math.min(100, Math.round((subtotalNgwee / FREE_DELIVERY_THRESHOLD_NGEWEE) * 100));
}

function remainingForFreeDelivery(subtotalNgwee: number): number {
  return Math.max(0, FREE_DELIVERY_THRESHOLD_NGEWEE - subtotalNgwee);
}

export function VendorGroups({
  groups,
  noticesByListingId,
  labels,
  lineLabels,
  onQtyChange,
  onRemove,
}: VendorGroupsProps) {
  return (
    <div className="flex flex-col gap-4" data-testid="cart-vendor-groups">
      {groups.map((group) => {
        const progress = deliveryProgress(group.subtotal_ngwee);
        const remaining = remainingForFreeDelivery(group.subtotal_ngwee);

        return (
          <section
            key={group.vendor_id}
            data-testid={`cart-vendor-group-${group.vendor_id}`}
            className="flex flex-col gap-3"
          >
            <header className="flex flex-col gap-1">
              <p className="text-sm font-semibold text-text">
                {labels.vendorGroup}
                <span className="text-text-2"> {group.vendor_id.slice(0, 8)}</span>
              </p>
              <p className="font-mono text-sm text-text-2">
                {labels.vendorSubtotal.replace("{amount}", formatK(group.subtotal_ngwee))}
              </p>
            </header>

            <div
              className="flex flex-col gap-2 rounded bg-bg-2 p-3"
              data-testid={`cart-delivery-nudge-${group.vendor_id}`}
            >
              <p className="text-xs text-text-2">
                {labels.deliveryThreshold.replace(
                  "{threshold}",
                  formatK(FREE_DELIVERY_THRESHOLD_NGEWEE),
                )}
              </p>
              {group.delivery_eligible ? (
                <p
                  className="text-sm font-medium text-success"
                  data-testid="cart-free-delivery-unlocked"
                >
                  {labels.freeDeliveryUnlocked}
                </p>
              ) : (
                <>
                  <p className="text-sm text-text-2">
                    {labels.deliveryHint.replace("{amount}", formatK(remaining))}
                  </p>
                  <div
                    className="h-2 overflow-hidden rounded-pill bg-border"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={progress}
                    aria-label={labels.freeDeliveryProgress
                      .replace("{amount}", formatK(group.subtotal_ngwee))
                      .replace("{threshold}", formatK(FREE_DELIVERY_THRESHOLD_NGEWEE))}
                  >
                    <div
                      className="h-full bg-primary transition-[width] duration-fast ease-std"
                      style={{ width: `${progress}%` }}
                      data-testid="cart-free-delivery-progress"
                    />
                  </div>
                  <p className="text-xs text-text-3">
                    {labels.freeDeliveryProgress
                      .replace("{amount}", formatK(group.subtotal_ngwee))
                      .replace("{threshold}", formatK(FREE_DELIVERY_THRESHOLD_NGEWEE))}
                  </p>
                </>
              )}
              {group.delivery_eligible ? (
                <p className="text-xs text-text-3" data-testid="cart-free-delivery-eligible">
                  {labels.deliveryEligible}
                </p>
              ) : null}
              <p className="text-xs text-text-3" data-testid="cart-delivery-scope-note">
                {labels.deliveryScopeNote}
              </p>
            </div>

            <div className="flex flex-col gap-3">
              {group.items.map((item) => (
                <CartLineItem
                  key={item.id}
                  item={item}
                  notice={noticesByListingId[item.listing_id]}
                  labels={lineLabels}
                  onQtyChange={onQtyChange}
                  onRemove={onRemove}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export function indexNoticesByListing(notices: ChangeNotice[]): Record<string, ChangeNotice> {
  return notices.reduce<Record<string, ChangeNotice>>((acc, notice) => {
    acc[notice.listing_id] = notice;
    return acc;
  }, {});
}

export type CartPageLabels = {
  title: string;
  emptyTitle: string;
  emptyBody: string;
  emptyTrust: CartEmptyTrustLabels;
  browseCta: string;
  itemCount: string;
  subtotal: string;
  total: string;
  checkoutCta: string;
  updateError: string;
  vendor: VendorGroupLabels;
  line: CartLineItemLabels;
  notices: ChangeNoticeLabels;
  miniCart: MiniCartLabels;
};

export type CartEmptyStateLabels = Pick<
  CartPageLabels,
  "emptyTitle" | "emptyBody" | "emptyTrust" | "browseCta"
>;

type CartPageViewProps = {
  locale: string;
  labels: CartPageLabels;
};

export function CartEmptyState({
  locale,
  labels,
}: {
  locale: string;
  labels: CartEmptyStateLabels;
}) {
  return (
    <section
      className="rounded-lg border border-border bg-bg-2/70 px-3 py-4 sm:px-6"
      data-testid="cart-empty-panel"
    >
      <EmptyState
        title={labels.emptyTitle}
        body={labels.emptyBody}
        data-testid="cart-empty-state"
        action={
          <Link
            href={`/${locale}`}
            className="inline-flex h-11 min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
          >
            {labels.browseCta}
          </Link>
        }
      />
      <CartEmptyTrustList labels={labels.emptyTrust} />
    </section>
  );
}

function CartPageBody({ locale, labels }: CartPageViewProps) {
  const { cart, notices, loading } = useCartStore();
  const { refresh, updateQty, removeItem } = useCartActions();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleQtyChange = useCallback(
    async (listingId: string, qty: number) => {
      setErrorMessage(null);
      try {
        await updateQty(listingId, qty);
      } catch {
        setErrorMessage(labels.updateError);
        throw new Error(labels.updateError);
      }
    },
    [labels.updateError, updateQty],
  );

  const handleRemove = useCallback(
    async (listingId: string) => {
      setErrorMessage(null);
      await removeItem(listingId);
    },
    [removeItem],
  );

  const itemCount = getCartItemCount(cart);
  const titleByListingId =
    cart?.items.reduce<Record<string, string>>((acc, item) => {
      acc[item.listing_id] = item.title_override ?? item.listing_id;
      return acc;
    }, {}) ?? {};

  if (!loading && (!cart || itemCount === 0)) {
    return <CartEmptyState locale={locale} labels={labels} />;
  }

  return (
    <div className="flex flex-col gap-4" data-testid="cart-page">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-2xl text-text">{labels.title}</h1>
        {cart ? (
          <p className="text-sm text-text-2" data-testid="cart-item-count">
            {labels.itemCount.replace("{count}", String(itemCount))}
          </p>
        ) : null}
      </header>

      {errorMessage ? (
        <p
          className="rounded border border-danger/30 bg-danger/10 p-3 text-sm text-danger"
          role="alert"
        >
          {errorMessage}
        </p>
      ) : null}

      <ChangeNotices
        notices={notices}
        labels={labels.notices}
        titleByListingId={titleByListingId}
      />

      {cart ? (
        <>
          <VendorGroups
            groups={cart.vendor_groups}
            noticesByListingId={indexNoticesByListing(notices)}
            labels={labels.vendor}
            lineLabels={labels.line}
            onQtyChange={handleQtyChange}
            onRemove={handleRemove}
          />

          <footer className="sticky bottom-20 flex flex-col gap-3 rounded border border-border bg-surface p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium text-text">{labels.total}</span>
              <span
                className="font-mono text-lg font-semibold text-text"
                data-testid="cart-subtotal"
              >
                {formatK(cart.subtotal_ngwee)}
              </span>
            </div>
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              loading={false}
              loadingLabel={labels.checkoutCta}
              disabled={itemCount === 0}
              onClick={() => {
                window.location.href = `/${locale}/checkout`;
              }}
            >
              {labels.checkoutCta}
            </Button>
          </footer>
        </>
      ) : (
        <div data-testid="cart-loading">
          <p className="sr-only" aria-live="polite">
            {labels.line.updating}
          </p>
          <div className="flex flex-col gap-3 motion-stagger" aria-hidden="true">
            {[0, 1].map((groupIndex) => (
              <section key={groupIndex} className="flex flex-col gap-3">
                <Skeleton shape="line" width="10rem" />
                <Skeleton height="4rem" />
                {[0, 1].map((lineIndex) => (
                  <div key={lineIndex} className="flex gap-3">
                    <Skeleton width="4rem" height="4rem" />
                    <div className="flex flex-1 flex-col gap-2 py-1">
                      <Skeleton shape="line" width="75%" />
                      <Skeleton shape="line" width="40%" />
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function CartPageView({ locale, labels }: CartPageViewProps) {
  return (
    <CartProvider>
      <CartPageBody locale={locale} labels={labels} />
      <CartHost locale={locale} labels={labels.miniCart} />
    </CartProvider>
  );
}
