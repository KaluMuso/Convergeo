import type { TimelineStep } from "./orders-api";

export type OrderTimelineLabels = {
  title: string;
  steps: Record<string, string>;
  escrow: {
    held: string;
    released: string;
    refunded: string;
    cod: string;
    strip?: { paid: string; held: string; released: string };
  };
  /** Plain-language "what this means" per step key (camelCase), shown on the current step. */
  explain?: Record<string, string>;
  /** Badge on the current step, e.g. "Now". */
  now?: string;
};

type OrderTimelineProps = {
  timeline: TimelineStep[];
  labels: OrderTimelineLabels;
  paymentMode?: "cod" | "prepaid";
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

type EscrowStripPhase = "paid" | "held" | "released";

const STRIP_STEPS: EscrowStripPhase[] = ["paid", "held", "released"];

function stepLabel(stepKey: string, labels: OrderTimelineLabels): string {
  const mapped = STEP_LABEL_KEY[stepKey];
  if (mapped && labels.steps[mapped]) {
    return labels.steps[mapped];
  }
  return stepKey;
}

function explainLabel(stepKey: string, labels: OrderTimelineLabels): string | null {
  const mapped = STEP_LABEL_KEY[stepKey];
  return (mapped && labels.explain?.[mapped]) || null;
}

function escrowLabel(copyKey: string, labels: OrderTimelineLabels): string | null {
  if (copyKey === "none" || copyKey === "strip") {
    return null;
  }
  const copy = labels.escrow[copyKey as keyof OrderTimelineLabels["escrow"]];
  return typeof copy === "string" ? copy : null;
}

function escrowStripPhase(timeline: TimelineStep[]): EscrowStripPhase | null {
  const refundStep = timeline.find(
    (step) => step.step_key === "refunded" && step.escrow_copy_key === "refunded",
  );
  if (refundStep && refundStep.state !== "skipped") {
    return null;
  }
  const completed = timeline.find((step) => step.step_key === "completed");
  if (
    completed &&
    completed.escrow_copy_key === "released" &&
    (completed.state === "current" || completed.state === "completed")
  ) {
    return "released";
  }
  const paymentHeld = timeline.find((step) => step.step_key === "payment_held");
  return paymentHeld?.state === "completed" ? "held" : "paid";
}

export function OrderTimeline({ timeline, labels, paymentMode }: OrderTimelineProps) {
  const visibleSteps = timeline.filter((step) => step.state !== "skipped");
  const stripLabels = labels.escrow.strip;
  const stripPhase = paymentMode === "prepaid" && stripLabels ? escrowStripPhase(timeline) : null;
  const showEscrowStrip = Boolean(stripLabels && stripPhase);
  const activeStripIndex = stripPhase ? STRIP_STEPS.indexOf(stripPhase) : -1;

  return (
    <section aria-labelledby="order-timeline-heading" className="space-y-3">
      <h3 id="order-timeline-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>
      {showEscrowStrip && stripLabels && stripPhase ? (
        <nav
          aria-label={`${stripLabels.paid} → ${stripLabels.held} → ${stripLabels.released}`}
          className="rounded-card border border-primary/20 bg-primary/5 px-3 py-2.5"
          data-testid="order-escrow-strip"
        >
          <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            {STRIP_STEPS.map((stepKey, index) => {
              const rank = STRIP_STEPS.indexOf(stepKey);
              const state =
                rank < activeStripIndex
                  ? "completed"
                  : rank === activeStripIndex
                    ? "current"
                    : "upcoming";
              return (
                <li
                  key={stepKey}
                  aria-current={state === "current" ? "step" : undefined}
                  className="flex min-w-0 items-center gap-1.5"
                >
                  {index > 0 ? (
                    <span aria-hidden className="shrink-0 text-xs text-text-2">
                      →
                    </span>
                  ) : null}
                  <span
                    className={[
                      "text-xs leading-tight",
                      state === "completed"
                        ? "font-medium text-primary"
                        : state === "current"
                          ? "font-semibold text-display-ink"
                          : "text-text-2",
                    ].join(" ")}
                  >
                    {state === "completed" ? "✓ " : null}
                    {stripLabels[stepKey]}
                  </span>
                </li>
              );
            })}
          </ol>
        </nav>
      ) : null}
      <ol className="space-y-3">
        {visibleSteps.map((step) => {
          const escrow = escrowLabel(step.escrow_copy_key, labels);
          const hideEscrowLine =
            showEscrowStrip &&
            (step.escrow_copy_key === "held" || step.escrow_copy_key === "released");
          const isCurrent = step.state === "current";
          const isCompleted = step.state === "completed";

          return (
            <li
              key={step.step_key}
              aria-current={isCurrent ? "step" : undefined}
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
                  <div className="flex flex-wrap items-center gap-2">
                    <p
                      className={[
                        "text-sm font-medium",
                        isCurrent || isCompleted ? "text-display-ink" : "text-text-2",
                      ].join(" ")}
                    >
                      {stepLabel(step.step_key, labels)}
                    </p>
                    {isCurrent && labels.now ? (
                      <span className="rounded-full bg-primary-tint px-2 py-0.5 text-xs font-medium text-primary-deep">
                        {labels.now}
                      </span>
                    ) : null}
                  </div>
                  {isCurrent && explainLabel(step.step_key, labels) ? (
                    <p
                      className="text-sm text-text-2"
                      data-testid={`order-timeline-explain-${step.step_key}`}
                    >
                      {explainLabel(step.step_key, labels)}
                    </p>
                  ) : null}
                  {escrow && !hideEscrowLine ? (
                    <p className="text-xs text-text-2">{escrow}</p>
                  ) : null}
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
