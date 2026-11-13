import type { ReactNode } from "react";

export type NextStepItem = {
  title: string;
  body?: ReactNode;
};

type NextStepsProps = {
  heading: string;
  headingId: string;
  steps: NextStepItem[];
  /** Index of the step the buyer is on now (rendered as filled); -1 = none started. */
  activeIndex?: number;
  testId?: string;
  headingAs?: "h2" | "h3";
};

/**
 * Numbered "what happens next" list used on review, confirmation and order
 * pages. Plain ordered list so screen readers announce position; the number
 * discs are decorative (aria-hidden) and use tokens only.
 */
export function NextSteps({
  heading,
  headingId,
  steps,
  activeIndex = -1,
  testId,
  headingAs: Heading = "h3",
}: NextStepsProps) {
  return (
    <section
      aria-labelledby={headingId}
      className="space-y-3 rounded-card border border-border bg-surface p-4"
      data-testid={testId}
    >
      <Heading id={headingId} className="font-body text-sm font-semibold text-text">
        {heading}
      </Heading>
      <ol className="space-y-3">
        {steps.map((step, index) => {
          const active = index <= activeIndex;
          return (
            <li key={step.title} className="flex items-start gap-3">
              <span
                aria-hidden
                className={[
                  "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs font-semibold",
                  active
                    ? "bg-primary text-[var(--primary-btn-fg)]"
                    : "border border-border bg-bg-2 text-text-2",
                ].join(" ")}
              >
                {index + 1}
              </span>
              <div className="min-w-0 space-y-0.5">
                <p className="font-body text-sm font-medium text-text">{step.title}</p>
                {step.body ? <p className="font-body text-sm text-text-2">{step.body}</p> : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
