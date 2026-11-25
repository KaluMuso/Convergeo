"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { IconChevronDown } from "@vergeo/ui/src/icons";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { PageHeader } from "@vergeo/ui/src/page-header";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchStorefrontConfigClient } from "../../../../../lib/storefront-config";

import { CartPageSkeleton } from "./cart-page-skeleton";
import { ChangeNotices, type ChangeNoticeLabels } from "./change-notices";
import { CartLineItem, type CartLineItemLabels } from "./line-items";
import {
  type ChangeNotice,
  type CartEmptyTrustLabels,
  type CartTicketLine,
  type VendorGroup,
  CartEmptyTrustList,
  CartProvider,
  getCartItemCount,
  removeCartTicketLine,
  useCartActions,
  useCartStore,
  vendorGroupLabel,
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
  /** e.g. "Seller {index} of {total}" — shown when multi-seller. */
  sellerIndex?: string;
  /** W8: "Free gift: {title} × {qty}" and "Worth {value} — free with your offer". */
  offerGift?: string;
  offerGiftWorth?: string;
};

type VendorGroupsProps = {
  locale?: string;
  groups: VendorGroup[];
  noticesByListingId: Record<string, ChangeNotice>;
  labels: VendorGroupLabels;
  lineLabels: CartLineItemLabels;
  onQtyChange: (listingId: string, qty: number) => Promise<void>;
  onRemove: (listingId: string) => Promise<void>;
  onSaveForLater?: (listingId: string) => Promise<void>;
  /**
   * Free-delivery threshold from the public config API. `null`/undefined when
   * unavailable — the threshold copy and progress bar are then hidden (no invented value).
   */
  freeDeliveryThresholdNgwee?: number | null;
};

export function deliveryProgress(subtotalNgwee: number, thresholdNgwee: number): number {
  return Math.min(100, Math.round((subtotalNgwee / thresholdNgwee) * 100));
}

export function remainingForFreeDelivery(subtotalNgwee: number, thresholdNgwee: number): number {
  return Math.max(0, thresholdNgwee - subtotalNgwee);
}

export function VendorGroups({
  locale = "en",
  groups,
  noticesByListingId,
  labels,
  lineLabels,
  onQtyChange,
  onRemove,
  onSaveForLater,
  freeDeliveryThresholdNgwee = null,
}: VendorGroupsProps) {
  const threshold =
    typeof freeDeliveryThresholdNgwee === "number" && freeDeliveryThresholdNgwee > 0
      ? freeDeliveryThresholdNgwee
      : null;
  const multiSeller = groups.length > 1;

  return (
    <div className="flex flex-col gap-4" data-testid="cart-vendor-groups">
      {groups.map((group, index) => {
        const progress = threshold === null ? 0 : deliveryProgress(group.subtotal_ngwee, threshold);
        const remaining =
          threshold === null ? 0 : remainingForFreeDelivery(group.subtotal_ngwee, threshold);
        const sellerIndexLabel =
          multiSeller && labels.sellerIndex
            ? labels.sellerIndex
                .replace("{index}", String(index + 1))
                .replace("{total}", String(groups.length))
            : null;

        return (
          <section
            key={group.vendor_id}
            data-testid={`cart-vendor-group-${group.vendor_id}`}
            className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:p-4"
            style={{ borderRadius: "var(--r)" }}
          >
            <header className="flex flex-col gap-1 border-b border-border pb-3">
              {sellerIndexLabel ? (
                <p className="text-xs font-medium uppercase tracking-wide text-text-3">
                  {sellerIndexLabel}
                </p>
              ) : null}
              <p className="text-sm font-semibold text-text">
                {labels.vendorGroup}
                <span
                  className={group.vendor_name?.trim() ? "text-text-2" : "font-mono text-text-2"}
                  data-testid={`cart-vendor-name-${group.vendor_id}`}
                >
                  {" "}
                  {vendorGroupLabel(group)}
                </span>
              </p>
              <p className="font-mono text-sm text-text-2">
                {labels.vendorSubtotal.replace("{amount}", formatK(group.subtotal_ngwee))}
              </p>
            </header>

            <div
              className="flex flex-col gap-2 rounded bg-bg-2 p-3"
              data-testid={`cart-delivery-nudge-${group.vendor_id}`}
            >
              {threshold !== null ? (
                <p className="text-xs text-text-2">
                  {labels.deliveryThreshold.replace("{threshold}", formatK(threshold))}
                </p>
              ) : null}
              {group.delivery_eligible ? (
                <p
                  className="text-sm font-medium text-success"
                  data-testid="cart-free-delivery-unlocked"
                >
                  {labels.freeDeliveryUnlocked}
                </p>
              ) : threshold === null ? null : (
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
                      .replace("{threshold}", formatK(threshold))}
                  >
                    <div
                      className="h-full bg-primary transition-[width] duration-fast ease-std motion-reduce:transition-none"
                      style={{ width: `${progress}%` }}
                      data-testid="cart-free-delivery-progress"
                    />
                  </div>
                  <p className="text-xs text-text-3">
                    {labels.freeDeliveryProgress
                      .replace("{amount}", formatK(group.subtotal_ngwee))
                      .replace("{threshold}", formatK(threshold))}
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
                  locale={locale}
                  notice={noticesByListingId[item.listing_id]}
                  labels={lineLabels}
                  onQtyChange={onQtyChange}
                  onRemove={onRemove}
                  onSaveForLater={onSaveForLater}
                />
              ))}
              {labels.offerGift
                ? (group.gifts ?? []).map((gift) => (
                    <div
                      key={`${gift.offer_id}-${gift.listing_id}`}
                      className="flex items-start justify-between gap-3 rounded border border-success/40 bg-success/10 p-3"
                      data-testid={`cart-offer-gift-${gift.listing_id}`}
                    >
                      <div className="min-w-0">
                        <p className="m-0 truncate text-sm font-medium text-text">
                          {(labels.offerGift ?? "")
                            .replace("{title}", gift.title ?? "")
                            .replace("{qty}", String(gift.qty))}
                        </p>
                        {labels.offerGiftWorth ? (
                          <p className="m-0 text-xs text-text-2">
                            {labels.offerGiftWorth.replace(
                              "{value}",
                              formatK(gift.qty * gift.reference_unit_price_ngwee),
                            )}
                          </p>
                        ) : null}
                      </div>
                      <p className="m-0 shrink-0 font-mono text-sm font-semibold text-success">
                        {formatK(0)}
                      </p>
                    </div>
                  ))
                : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export type TicketGroupLabels = {
  /** Item-type captions shown on every group: "Products", "Event tickets". */
  typeProducts: string;
  typeEventTickets: string;
  /** "{type} × {qty}" under the event title. */
  line: string;
  remove: string;
  /** "Remove {title}" for screen readers. */
  removeLabel: string;
  unavailable: string;
  platformFee: string;
  prepaidOnly: string;
};

export function ItemTypeCaption({ label, testId }: { label: string; testId: string }) {
  return (
    <p
      className="m-0 text-xs font-semibold uppercase tracking-wide text-text-3"
      data-testid={testId}
    >
      {label}
    </p>
  );
}

export function TicketLinesGroup({
  lines,
  unavailableIds,
  labels,
  onRemove,
}: {
  lines: CartTicketLine[];
  unavailableIds: string[];
  labels: TicketGroupLabels;
  onRemove: (lineId: string) => Promise<void>;
}) {
  if (lines.length === 0) {
    return null;
  }
  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:p-4"
      style={{ borderRadius: "var(--r)" }}
      data-testid="cart-ticket-group"
      aria-label={labels.typeEventTickets}
    >
      <ItemTypeCaption label={labels.typeEventTickets} testId="cart-type-event-tickets" />
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {lines.map((line) => {
          const unavailable = unavailableIds.includes(line.id);
          const saved =
            typeof line.list_line_total_ngwee === "number" &&
            line.list_line_total_ngwee > line.line_total_ngwee;
          return (
            <li
              key={line.id}
              className="flex items-start justify-between gap-3 border-t border-border pt-3 first:border-t-0 first:pt-0"
              data-testid={`cart-ticket-line-${line.id}`}
            >
              <div className="min-w-0">
                <p className="m-0 break-words text-sm font-medium text-text">{line.event_title}</p>
                <p className="m-0 text-xs text-text-2">
                  {labels.line.replace("{type}", line.type_name).replace("{qty}", String(line.qty))}
                </p>
                {unavailable ? (
                  <p className="m-0 text-xs font-medium text-danger" role="status">
                    {labels.unavailable}
                  </p>
                ) : null}
                <button
                  type="button"
                  className="mt-1 min-h-11 text-sm text-text-2 underline"
                  aria-label={labels.removeLabel.replace("{title}", line.event_title)}
                  onClick={() => void onRemove(line.id)}
                >
                  {labels.remove}
                </button>
              </div>
              <div className="shrink-0 text-right font-mono text-sm">
                {saved ? (
                  <p className="m-0 text-xs text-text-3 line-through">
                    {formatK(line.list_line_total_ngwee ?? 0)}
                  </p>
                ) : null}
                <p className="m-0 font-semibold text-text">{formatK(line.line_total_ngwee)}</p>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="m-0 text-xs text-text-3" data-testid="cart-ticket-prepaid">
        {labels.prepaidOnly}
      </p>
    </section>
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
  loading: string;
  emptyTitle: string;
  emptyBody: string;
  emptyTrust: CartEmptyTrustLabels;
  browseCta: string;
  subtotal: string;
  total: string;
  checkoutCta: string;
  updateError: string;
  loadErrorTitle: string;
  loadErrorBody: string;
  loadErrorRetry: string;
  multiSellerNote: string;
  escrowTeaser: string;
  /** 3-step escrow ladder (You pay → Held → Released); reuses checkout.review keys. */
  escrowSteps: string[];
  stockUnavailableNotice: string;
  /** Shown when checkout sent the buyer back because their stock hold lapsed. */
  reservationExpiredNotice: string;
  summaryHeading: string;
  /** W8: "You save" row in the order summary when an offer applied. */
  offerSavings?: string;
  /** Unified cart: line-type captions and the event-ticket group. */
  tickets?: TicketGroupLabels;
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
        illustration="empty-cart"
        data-testid="cart-empty-state"
        action={
          <LinkButton href={`/${locale}`} variant="primary" LinkComponent={Link}>
            {labels.browseCta}
          </LinkButton>
        }
      />
      <CartEmptyTrustList labels={labels.emptyTrust} />
    </section>
  );
}

function CartLoadError({
  labels,
  onRetry,
}: {
  labels: Pick<CartPageLabels, "loadErrorTitle" | "loadErrorBody" | "loadErrorRetry">;
  onRetry: () => void;
}) {
  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5"
      data-testid="cart-load-error"
      role="alert"
    >
      <h2 className="font-display text-lg font-semibold text-text">{labels.loadErrorTitle}</h2>
      <p className="text-sm text-text-2">{labels.loadErrorBody}</p>
      <Button
        type="button"
        variant="primary"
        size="md"
        className="w-fit"
        loading={false}
        loadingLabel={labels.loadErrorRetry}
        data-testid="cart-load-error-retry"
        onClick={onRetry}
      >
        {labels.loadErrorRetry}
      </Button>
    </section>
  );
}

function CartPageBody({ locale, labels }: CartPageViewProps) {
  const { cart, notices, loading, loadError } = useCartStore();
  const { refresh, updateQty, removeItem, saveForLater } = useCartActions();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const searchParams = useSearchParams();
  const stockNotice = searchParams.get("notice") === "stock_unavailable";
  const reservationNotice = searchParams.get("notice") === "reservation_expired";
  const [freeDeliveryThresholdNgwee, setFreeDeliveryThresholdNgwee] = useState<number | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let active = true;
    void fetchStorefrontConfigClient().then((config) => {
      if (active) {
        setFreeDeliveryThresholdNgwee(config.freeDeliveryThresholdNgwee);
      }
    });
    return () => {
      active = false;
    };
  }, []);

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

  const handleRemoveTicket = useCallback(
    async (lineId: string) => {
      setErrorMessage(null);
      try {
        await removeCartTicketLine(lineId);
      } catch {
        setErrorMessage(labels.updateError);
      }
    },
    [labels.updateError],
  );

  const handleSaveForLater = useCallback(
    async (listingId: string) => {
      setErrorMessage(null);
      try {
        await saveForLater(listingId);
      } catch {
        setErrorMessage(labels.updateError);
      }
    },
    [labels.updateError, saveForLater],
  );

  // `cart.itemCount` is a true ICU plural, so it cannot travel as a template
  // string the way the other cart labels do — it is formatted here, against the
  // shop layout's client provider, so Bemba/Nyanja plural rules still apply.
  const tCheckout = useTranslations("checkout");
  const itemCount = getCartItemCount(cart);
  const titleByListingId =
    cart?.items.reduce<Record<string, string>>((acc, item) => {
      acc[item.listing_id] = item.title_override ?? item.listing_id;
      return acc;
    }, {}) ?? {};

  const multiSeller = (cart?.vendor_groups.length ?? 0) > 1;

  const checkoutDisabled = useMemo(() => {
    if (!cart || itemCount === 0) {
      return true;
    }
    return (
      notices.some((notice) => notice.kind === "out_of_stock") ||
      (cart.unavailable_ticket_line_ids?.length ?? 0) > 0
    );
  }, [cart, itemCount, notices]);

  if (loading && !cart) {
    return <CartPageSkeleton loadingLabel={labels.loading} />;
  }

  if (loadError && !cart) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={labels.title} className="border-0 pb-0" />
        <CartLoadError
          labels={labels}
          onRetry={() => {
            void refresh();
          }}
        />
      </div>
    );
  }

  if (!loading && (!cart || itemCount === 0)) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={labels.title} className="border-0 pb-0" />
        <CartEmptyState locale={locale} labels={labels} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] lg:items-start lg:gap-8">
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader
          title={labels.title}
          subtitle={cart ? tCheckout("cart.itemCount", { count: itemCount }) : undefined}
          className="border-0 pb-2"
          data-testid="cart-page-header"
        />

        {stockNotice ? (
          <p
            className="rounded border border-warning/40 bg-warning/10 p-3 text-sm text-text"
            role="status"
            data-testid="cart-stock-unavailable-notice"
          >
            {labels.stockUnavailableNotice}
          </p>
        ) : null}

        {reservationNotice ? (
          <p
            className="rounded border border-warning/40 bg-warning/10 p-3 text-sm text-text"
            role="status"
            data-testid="cart-reservation-expired-notice"
          >
            {labels.reservationExpiredNotice}
          </p>
        ) : null}

        {errorMessage ? (
          <p
            className="rounded border border-danger/30 bg-danger/10 p-3 text-sm text-danger"
            role="alert"
          >
            {errorMessage}
          </p>
        ) : null}

        {multiSeller ? (
          <p
            className="rounded border border-border bg-bg-2 px-3 py-2 text-sm text-text-2"
            data-testid="cart-multi-seller-note"
          >
            {labels.multiSellerNote}
          </p>
        ) : null}

        <ChangeNotices
          notices={notices}
          labels={labels.notices}
          titleByListingId={titleByListingId}
        />

        {cart && labels.tickets && cart.vendor_groups.length > 0 ? (
          <ItemTypeCaption label={labels.tickets.typeProducts} testId="cart-type-products" />
        ) : null}
        {cart ? (
          <VendorGroups
            locale={locale}
            groups={cart.vendor_groups}
            noticesByListingId={indexNoticesByListing(notices)}
            labels={labels.vendor}
            lineLabels={labels.line}
            onQtyChange={handleQtyChange}
            onRemove={handleRemove}
            onSaveForLater={handleSaveForLater}
            freeDeliveryThresholdNgwee={freeDeliveryThresholdNgwee}
          />
        ) : null}
        {cart && labels.tickets ? (
          <TicketLinesGroup
            lines={cart.ticket_lines ?? []}
            unavailableIds={cart.unavailable_ticket_line_ids ?? []}
            labels={labels.tickets}
            onRemove={handleRemoveTicket}
          />
        ) : null}
      </div>

      {cart ? (
        <aside
          className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom,0px))] z-20 flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-2 lg:bottom-auto lg:top-20 lg:z-0 lg:shadow-1"
          data-testid="cart-order-summary"
          style={{ borderRadius: "var(--r)" }}
        >
          <h2 className="font-display text-lg font-semibold text-text">{labels.summaryHeading}</h2>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-text-2">{labels.subtotal}</span>
            <span className="font-mono text-sm text-text" data-testid="cart-subtotal-label">
              {formatK(cart.subtotal_ngwee)}
            </span>
          </div>
          {(cart.savings_ngwee ?? 0) > 0 && labels.offerSavings ? (
            <div
              className="flex items-center justify-between gap-3"
              data-testid="cart-offer-savings"
            >
              <span className="text-sm text-success">{labels.offerSavings}</span>
              <span className="font-mono text-sm text-success">
                {`-${formatK(cart.savings_ngwee ?? 0)}`}
              </span>
            </div>
          ) : null}
          {(cart.platform_fee_ngwee ?? 0) > 0 && labels.tickets ? (
            <div
              className="flex items-center justify-between gap-3"
              data-testid="cart-platform-fee"
            >
              <span className="text-sm text-text-2">{labels.tickets.platformFee}</span>
              <span className="font-mono text-sm text-text">
                {formatK(cart.platform_fee_ngwee ?? 0)}
              </span>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-3 border-t border-border pt-2">
            <span className="font-medium text-text">{labels.total}</span>
            <span
              className="font-mono text-lg font-semibold text-[var(--price)]"
              data-testid="cart-subtotal"
            >
              {formatK(cart.subtotal_ngwee + (cart.platform_fee_ngwee ?? 0))}
            </span>
          </div>
          <ol
            aria-label={labels.escrowTeaser}
            data-testid="cart-escrow-ladder"
            className="m-0 flex list-none flex-wrap items-center gap-x-2 gap-y-1 p-0 text-micro font-semibold uppercase tracking-wide text-text-2"
          >
            {labels.escrowSteps.map((step, index) => (
              <li key={index} className="flex items-center gap-2">
                {index > 0 ? (
                  <IconChevronDown aria-hidden className="-rotate-90 text-text-3" />
                ) : null}
                <span className="rounded border border-border bg-bg-2 px-2.5 py-1 text-text-2">
                  {step}
                </span>
              </li>
            ))}
          </ol>
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            loading={false}
            loadingLabel={labels.checkoutCta}
            disabled={checkoutDisabled}
            data-testid="cart-checkout-cta"
            onClick={() => {
              window.location.href = `/${locale}/checkout`;
            }}
          >
            {labels.checkoutCta}
          </Button>
        </aside>
      ) : null}
    </div>
  );
}

export function CartPageView({ locale, labels }: CartPageViewProps) {
  return (
    <CartProvider>
      {/*
       * `cart-page` marks the Cart page surface itself, NOT any one cart state.
       * It lives here — around every CartPageBody branch — precisely because it
       * previously sat on a single unconditional cart render and was lost when
       * that render was split into the loading / load-error / empty / populated
       * branches below: each branch returns early, so a per-branch attribute
       * silently drifts the moment a new branch is added. Anchoring it once, at
       * the surface boundary, keeps the contract true for every current and
       * future state. Do not move it onto a state-specific element.
       */}
      <div data-testid="cart-page">
        <CartPageBody locale={locale} labels={labels} />
      </div>
    </CartProvider>
  );
}
