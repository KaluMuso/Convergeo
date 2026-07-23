import Link from "next/link";

import { FulfillmentLogisticsPills, type LogisticsPillLabels } from "../plp/logistics-pills";

export type BuyerTrustPanelProps = {
  sellerStatusLabel: string;
  deliveryAvailable?: boolean;
  pickupAvailable?: boolean;
  logisticsPillLabels?: Pick<LogisticsPillLabels, "delivery" | "pickup">;
  returnsLabel: string;
  returnsHref: string;
  escrowLabel: string;
};

/**
 * Compact buyer-confidence strip placed near Add to Cart.
 * Delivery/pickup pills are omitted unless the listing actually supports them.
 * Escrow copy must not claim online payments are live when they are gated.
 */
export function BuyerTrustPanel({
  sellerStatusLabel,
  deliveryAvailable = false,
  pickupAvailable = false,
  logisticsPillLabels,
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
      {logisticsPillLabels ? (
        <FulfillmentLogisticsPills
          deliveryAvailable={deliveryAvailable}
          pickupAvailable={pickupAvailable}
          labels={logisticsPillLabels}
          testId="pdp-trust-logistics"
        />
      ) : null}
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
