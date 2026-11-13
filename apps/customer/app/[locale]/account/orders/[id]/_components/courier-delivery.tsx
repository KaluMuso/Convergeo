import { formatK } from "@vergeo/i18n";

import type { CourierDelivery, CourierDeliveryStatus } from "../../_components/orders-api";

export type CourierDeliveryLabels = {
  title: string;
  courier: string;
  reference: string;
  statuses: Record<CourierDeliveryStatus, string>;
  codDue: (amount: string) => string;
  handoverTitle: string;
  handoverBody: string;
  handoverAria: (code: string) => string;
  failedBody: string;
};

type CourierDeliveryBlockProps = {
  delivery: CourierDelivery;
  labels: CourierDeliveryLabels;
};

const IN_FLIGHT: ReadonlySet<CourierDeliveryStatus> = new Set([
  "requested",
  "accepted",
  "picked_up",
]);

/**
 * Courier status timeline + the customer's handover code (delivery
 * chain-of-custody v1). The API only returns `handover_code` to the order
 * owner and only while the dispatch is in flight; this component additionally
 * refuses to render a code for a closed dispatch.
 */
export function CourierDeliveryBlock({ delivery, labels }: CourierDeliveryBlockProps) {
  const showCode = Boolean(delivery.handover_code) && IN_FLIGHT.has(delivery.status);
  const steps = [...delivery.timeline].sort(
    (left, right) => new Date(left.at).getTime() - new Date(right.at).getTime(),
  );

  return (
    <section
      aria-labelledby="courier-delivery-heading"
      className="space-y-3 rounded border border-border bg-surface p-4"
      data-testid="courier-delivery"
      data-status={delivery.status}
    >
      <h3 id="courier-delivery-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>

      <dl className="space-y-1 text-sm">
        <div className="flex flex-wrap justify-between gap-2">
          <dt className="text-text-2">{labels.courier}</dt>
          <dd className="font-medium text-display-ink">{delivery.courier_name}</dd>
        </div>
        {delivery.courier_reference ? (
          <div className="flex flex-wrap justify-between gap-2">
            <dt className="text-text-2">{labels.reference}</dt>
            <dd className="font-mono text-display-ink">{delivery.courier_reference}</dd>
          </div>
        ) : null}
      </dl>

      {showCode && delivery.handover_code ? (
        <div className="space-y-1 rounded bg-bg-2 p-3" data-testid="handover-code">
          <p className="text-sm font-medium text-display-ink">{labels.handoverTitle}</p>
          <p
            aria-label={labels.handoverAria(delivery.handover_code)}
            className="font-mono text-2xl tracking-widest text-display-ink"
          >
            {delivery.handover_code}
          </p>
          <p className="text-xs text-text-2">{labels.handoverBody}</p>
        </div>
      ) : null}

      {delivery.cod_amount_ngwee > 0 && IN_FLIGHT.has(delivery.status) ? (
        <p className="text-sm text-display-ink">
          {labels.codDue(formatK(delivery.cod_amount_ngwee))}
        </p>
      ) : null}

      <ol className="space-y-2" aria-label={labels.title}>
        {steps.map((step) => (
          <li
            key={`${step.status}-${step.at}`}
            className="rounded border border-border bg-bg-2 px-3 py-2 text-sm"
          >
            <p className="font-medium text-display-ink">{labels.statuses[step.status]}</p>
            <time className="mt-1 block font-mono text-xs text-text-2" dateTime={step.at}>
              {new Date(step.at).toLocaleString()}
            </time>
          </li>
        ))}
      </ol>

      {delivery.status === "failed" ? (
        <p className="text-sm text-text-2">{labels.failedBody}</p>
      ) : null}
    </section>
  );
}
