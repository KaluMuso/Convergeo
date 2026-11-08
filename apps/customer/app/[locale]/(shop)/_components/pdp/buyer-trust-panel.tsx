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
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 text-sm text-text-2"
      aria-label={sellerStatusLabel}
    >
      <p
        data-testid="pdp-trust-seller"
        className="m-0 flex items-center gap-2 font-semibold text-text"
      >
        <TrustGlyph path="M12 3 4.5 6v5.5c0 4.4 3.1 8.2 7.5 9.5 4.4-1.3 7.5-5.1 7.5-9.5V6L12 3Zm-3 9 2 2 4-4.5" />
        {sellerStatusLabel}
      </p>
      {/* Escrow is the signature promise — the copper-ringed seal marks it everywhere. */}
      <div className="flex items-start gap-3 rounded bg-primary-tint p-3 text-primary-deep">
        <span aria-hidden className="ds-seal">
          <svg
            viewBox="0 0 24 24"
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6 10V8a6 6 0 1 1 12 0v2M5 10h14v10H5zM12 14v2.5" />
          </svg>
        </span>
        <p data-testid="pdp-trust-escrow" className="m-0 font-medium leading-snug">
          {escrowLabel}
        </p>
      </div>
      {logisticsPillLabels ? (
        <FulfillmentLogisticsPills
          deliveryAvailable={deliveryAvailable}
          pickupAvailable={pickupAvailable}
          labels={logisticsPillLabels}
          testId="pdp-trust-logistics"
        />
      ) : null}
      <Link
        href={returnsHref}
        data-testid="pdp-trust-returns"
        className="inline-flex min-h-11 items-center gap-2 font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        <TrustGlyph path="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4" />
        {returnsLabel}
      </Link>
    </aside>
  );
}

function TrustGlyph({ path }: { path: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="h-5 w-5 shrink-0 text-primary"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}
