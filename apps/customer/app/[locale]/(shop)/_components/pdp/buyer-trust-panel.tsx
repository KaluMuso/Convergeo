import Link from "next/link";

export type BuyerTrustPanelProps = {
  sellerStatusLabel: string;
  deliveryLabel?: string | null;
  pickupLabel?: string | null;
  returnsLabel: string;
  returnsHref: string;
  escrowLabel: string;
};

/**
 * Compact buyer-confidence strip placed near Add to Cart.
 * Delivery/pickup lines are omitted unless the listing actually supports them.
 * Escrow copy must not claim online payments are live when they are gated.
 */
export function BuyerTrustPanel({
  sellerStatusLabel,
  deliveryLabel,
  pickupLabel,
  returnsLabel,
  returnsHref,
  escrowLabel,
}: BuyerTrustPanelProps) {
  return (
    <aside
      data-testid="pdp-buyer-trust"
      className="flex flex-col gap-2 rounded border border-border bg-bg-2/60 px-3 py-3 text-sm text-text-2"
      style={{ borderRadius: "var(--r)" }}
      aria-label={sellerStatusLabel}
    >
      <p data-testid="pdp-trust-seller" className="font-medium text-text">
        {sellerStatusLabel}
      </p>
      {deliveryLabel ? (
        <p data-testid="pdp-trust-delivery">{deliveryLabel}</p>
      ) : null}
      {pickupLabel ? <p data-testid="pdp-trust-pickup">{pickupLabel}</p> : null}
      <p data-testid="pdp-trust-escrow">{escrowLabel}</p>
      <Link
        href={returnsHref}
        data-testid="pdp-trust-returns"
        className="inline-flex min-h-11 items-center font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {returnsLabel}
      </Link>
    </aside>
  );
}
