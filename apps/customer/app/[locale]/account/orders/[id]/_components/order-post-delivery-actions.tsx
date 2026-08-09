import Link from "next/link";

export type OrderPostDeliveryActionsLabels = {
  actionsTitle: string;
  requestReturn: string;
  openDispute: string;
};

type OrderPostDeliveryActionsProps = {
  locale: string;
  orderId: string;
  status: string;
  labels: OrderPostDeliveryActionsLabels;
};

const POST_DELIVERY_STATUSES = new Set(["shipped", "delivered", "completed"]);

export function shouldShowPostDeliveryActions(status: string): boolean {
  return POST_DELIVERY_STATUSES.has(status);
}

export function OrderPostDeliveryActions({
  locale,
  orderId,
  status,
  labels,
}: OrderPostDeliveryActionsProps) {
  if (!shouldShowPostDeliveryActions(status)) {
    return null;
  }

  return (
    <section
      className="space-y-3 rounded border border-border bg-surface p-4"
      aria-labelledby="order-post-delivery-actions"
      data-testid="order-post-delivery-actions"
    >
      <h3 id="order-post-delivery-actions" className="font-display text-h3 text-display-ink">
        {labels.actionsTitle}
      </h3>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Link
          href={`/${locale}/account/orders/${orderId}/return`}
          className="inline-flex min-h-11 flex-1 items-center justify-center rounded border border-border bg-bg px-4 text-sm font-medium text-primary transition-colors hover:bg-bg-2 motion-reduce:transition-none"
          data-testid="order-request-return"
        >
          {labels.requestReturn}
        </Link>
        <Link
          href={`/${locale}/account/orders/${orderId}/dispute`}
          className="inline-flex min-h-11 flex-1 items-center justify-center rounded border border-border bg-bg px-4 text-sm font-medium text-primary transition-colors hover:bg-bg-2 motion-reduce:transition-none"
          data-testid="order-open-dispute"
        >
          {labels.openDispute}
        </Link>
      </div>
    </section>
  );
}
