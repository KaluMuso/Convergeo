import type { TimelineStep } from "./orders-api";

export type OrderTimelineLabels = {
  title: string;
  steps: Record<string, string>;
  escrow: Record<string, string>;
};

type OrderTimelineProps = {
  timeline: TimelineStep[];
  labels: OrderTimelineLabels;
};

const STEP_LABEL_KEY: Record<string, keyof OrderTimelineLabels["steps"]> = {
  placed: "placed",
  payment_held: "paymentHeld",
  payment_cod: "paymentCod",
  confirmed: "confirmed",
  processing: "processing",
  ready: "ready",
  shipped: "shipped",
  delivered: "delivered",
  completed: "completed",
  cancelled: "cancelled",
  refunded: "refunded",
};

function stepLabel(stepKey: string, labels: OrderTimelineLabels): string {
  const mapped = STEP_LABEL_KEY[stepKey];
  if (mapped && labels.steps[mapped]) {
    return labels.steps[mapped];
  }
  return stepKey;
}

function escrowLabel(copyKey: string, labels: OrderTimelineLabels): string | null {
  if (copyKey === "none") {
    return null;
  }
  return labels.escrow[copyKey] ?? null;
}

export function OrderTimeline({ timeline, labels }: OrderTimelineProps) {
  const visibleSteps = timeline.filter((step) => step.state !== "skipped");

  return (
    <section aria-labelledby="order-timeline-heading" className="space-y-3">
      <h3 id="order-timeline-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>
      <ol className="space-y-3">
        {visibleSteps.map((step) => {
          const escrow = escrowLabel(step.escrow_copy_key, labels);
          const isCurrent = step.state === "current";
          const isCompleted = step.state === "completed";

          return (
            <li
              key={step.step_key}
              className={[
                "rounded border px-4 py-3",
                isCurrent ? "border-primary bg-bg-2" : "border-border bg-surface",
              ].join(" ")}
            >
              <div className="flex items-start gap-3">
                <span
                  aria-hidden
                  className={[
                    "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    isCompleted
                      ? "bg-primary text-surface"
                      : isCurrent
                        ? "border-2 border-primary text-primary"
                        : "border border-border text-text-2",
                  ].join(" ")}
                >
                  {isCompleted ? "✓" : "•"}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <p
                    className={[
                      "text-sm font-medium",
                      isCurrent || isCompleted ? "text-display-ink" : "text-text-2",
                    ].join(" ")}
                  >
                    {stepLabel(step.step_key, labels)}
                  </p>
                  {escrow ? <p className="text-xs text-text-2">{escrow}</p> : null}
                  {step.occurred_at ? (
                    <time className="font-mono text-xs text-text-2" dateTime={step.occurred_at}>
                      {new Date(step.occurred_at).toLocaleString()}
                    </time>
                  ) : null}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
