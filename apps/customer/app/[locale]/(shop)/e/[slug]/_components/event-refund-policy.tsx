import { refundPolicyMessageKey } from "../_lib/refund-policy";

export type EventRefundPolicyLabels = Record<string, string> & {
  heading: string;
};

type EventRefundPolicyProps = {
  refundPolicyKey: string | null | undefined;
  labels: EventRefundPolicyLabels;
};

export function EventRefundPolicy({ refundPolicyKey, labels }: EventRefundPolicyProps) {
  const key = refundPolicyMessageKey(refundPolicyKey);
  const body = labels[key] ?? labels.unknown;
  if (!body) {
    return null;
  }

  return (
    <section
      className="rounded-md border border-border bg-bg-2 px-4 py-3"
      aria-labelledby="event-refund-policy-heading"
      data-testid="event-refund-policy"
    >
      <h3
        id="event-refund-policy-heading"
        className="text-xs font-semibold uppercase tracking-[0.14em] text-text-3"
      >
        {labels.heading}
      </h3>
      <p className="mt-2 text-sm text-text-2">{body}</p>
    </section>
  );
}
