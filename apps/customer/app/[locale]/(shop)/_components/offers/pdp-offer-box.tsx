import { formatK } from "@vergeo/i18n";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

import { OfferAddAll, type OfferAddAllLabels } from "./offer-add-all";
import {
  offerBadgeLabel,
  type OfferBadge,
  type OfferBadgeLabels,
} from "./offer-badge";

type PublicOfferItem = {
  role: string;
  listing_id: string;
  qty: number;
  title: string | null;
  unit_price_ngwee: number;
};

export type PublicOffer = {
  id: string;
  offer_type: string;
  title: string;
  badge: OfferBadge;
  items: PublicOfferItem[];
  list_total_ngwee: number;
  pay_ngwee: number;
  savings_ngwee: number;
  gift_qty: number;
  gift_value_ngwee: number;
};

export type PdpOfferBoxLabels = {
  heading: string;
  /** "{title} × {qty}" */
  itemLine: string;
  /** "You pay {pay} instead of {list}" */
  youPay: string;
  /** "You save {amount}" */
  youSave: string;
  /** "Free: {title} × {qty} (worth {value})" */
  freeGift: string;
  badge: OfferBadgeLabels;
  addAll: OfferAddAllLabels;
};

/** W8: offers this listing takes part in. Empty when `bundles` is off. */
export async function fetchListingOffers(
  listingId: string,
): Promise<PublicOffer[]> {
  const url = absoluteApiUrl(
    `/offers/listing/${encodeURIComponent(listingId)}`,
  );
  if (!url) {
    return [];
  }
  try {
    const response = await fetch(url, {
      next: { revalidate: 60, tags: ["offers"] },
    });
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as { offers?: PublicOffer[] };
    return Array.isArray(payload.offers) ? payload.offers : [];
  } catch {
    return [];
  }
}

function fill(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.split(`{${key}}`).join(value),
    template,
  );
}

/** "Bundle & save" box on the PDP (server component; one small client button per offer). */
export async function PdpOfferBox({
  listingId,
  labels,
}: {
  listingId: string;
  labels: PdpOfferBoxLabels;
}) {
  const offers = await fetchListingOffers(listingId);
  if (offers.length === 0) {
    return null;
  }
  return (
    <section
      aria-labelledby="pdp-offers-heading"
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:p-4"
      data-testid="pdp-offer-box"
    >
      <h2
        id="pdp-offers-heading"
        className="m-0 text-base font-semibold text-text"
      >
        {labels.heading}
      </h2>
      {offers.map((offer) => {
        const badge = offerBadgeLabel(offer.badge, labels.badge);
        const paid = offer.items.filter((item) => item.role !== "reward");
        const gift = offer.items.find((item) => item.role === "reward");
        const addItems = paid.map((item) => ({
          listingId: item.listing_id,
          qty:
            offer.offer_type === "bxgy"
              ? (offer.badge.buy_qty ?? 1) * item.qty
              : offer.offer_type === "buy_n_pay_m"
                ? (offer.badge.buy_n ?? 1)
                : item.qty,
        }));
        // Gift offers and buy-N offers: the customer buys one trigger line.
        const toAdd =
          offer.offer_type === "bundle" ? addItems : addItems.slice(0, 1);
        return (
          <article
            key={offer.id}
            className="flex flex-col gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0"
            data-testid={`pdp-offer-${offer.id}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              {badge ? (
                <span className="inline-block rounded-pill bg-accent px-2.5 py-0.5 text-micro font-semibold uppercase tracking-wide text-surface">
                  {badge}
                </span>
              ) : null}
              <p className="m-0 text-sm font-medium text-text">{offer.title}</p>
            </div>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm text-text-2">
              {paid.map((item) => (
                <li
                  key={`${item.role}-${item.listing_id}`}
                  className="flex justify-between gap-2"
                >
                  <span className="min-w-0 truncate">
                    {fill(labels.itemLine, {
                      title: item.title ?? "",
                      qty: String(item.qty),
                    })}
                  </span>
                  <span className="shrink-0 font-mono">
                    {formatK(item.unit_price_ngwee)}
                  </span>
                </li>
              ))}
            </ul>
            {gift && offer.gift_qty > 0 ? (
              <p
                className="m-0 text-sm font-medium text-success"
                data-testid="pdp-offer-gift"
              >
                {fill(labels.freeGift, {
                  title: gift.title ?? "",
                  qty: String(offer.gift_qty),
                  value: formatK(offer.gift_value_ngwee),
                })}
              </p>
            ) : null}
            {offer.savings_ngwee > 0 ? (
              <p className="m-0 text-sm text-text" data-testid="pdp-offer-pay">
                {fill(labels.youPay, {
                  pay: formatK(offer.pay_ngwee),
                  list: formatK(offer.list_total_ngwee),
                })}{" "}
                <span className="font-semibold text-success">
                  {fill(labels.youSave, {
                    amount: formatK(offer.savings_ngwee),
                  })}
                </span>
              </p>
            ) : null}
            <OfferAddAll
              offerId={offer.id}
              items={toAdd}
              labels={labels.addAll}
            />
          </article>
        );
      })}
    </section>
  );
}
