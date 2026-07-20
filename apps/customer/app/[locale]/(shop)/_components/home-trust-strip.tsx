import { IconChevronDown } from "@vergeo/ui/src/icons";

/**
 * Compact post-hero trust strip for the customer homepage (CUST-HOME-01 / audit §4.1).
 * Escrow ladder lives here (not in the hero). Copy stays payment-gated honest —
 * no “MoMo/card live” claims.
 */

export type HomeTrustStripLabels = {
  ariaLabel: string;
  sellers: string;
  fulfillment: string;
  returns: string;
  escrow: string;
  escrowStep1: string;
  escrowStep2: string;
  escrowStep3: string;
};

type HomeTrustStripProps = {
  labels: HomeTrustStripLabels;
};

const ITEMS: Array<{
  key: keyof Pick<HomeTrustStripLabels, "sellers" | "fulfillment" | "returns" | "escrow">;
  testId: string;
}> = [
  { key: "sellers", testId: "home-trust-sellers" },
  { key: "fulfillment", testId: "home-trust-fulfillment" },
  { key: "returns", testId: "home-trust-returns" },
  { key: "escrow", testId: "home-trust-escrow" },
];

export function HomeTrustStrip({ labels }: HomeTrustStripProps) {
  const escrowSteps = [labels.escrowStep1, labels.escrowStep2, labels.escrowStep3];

  return (
    <section
      data-testid="home-trust-strip"
      aria-label={labels.ariaLabel}
      className="flex flex-col gap-3"
    >
      <ol
        data-testid="home-trust-escrow-ladder"
        className="m-0 flex list-none flex-wrap items-center gap-x-2 gap-y-1 p-0 text-micro font-semibold uppercase tracking-wide text-text-2"
      >
        {escrowSteps.map((step, index) => (
          <li key={`escrow-step-${index}`} className="flex items-center gap-2">
            {index > 0 ? <IconChevronDown aria-hidden className="-rotate-90 text-text-3" /> : null}
            <span className="rounded border border-border bg-bg-2 px-2.5 py-1 text-text-2">
              {step}
            </span>
          </li>
        ))}
      </ol>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 lg:grid-cols-4 lg:gap-3">
        {ITEMS.map((item) => (
          <li
            key={item.key}
            data-testid={item.testId}
            className="flex min-h-11 items-start gap-2 rounded border border-border bg-surface px-3 py-2.5 text-sm text-text-2"
          >
            <span
              aria-hidden
              className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-primary"
            />
            <span>{labels[item.key]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
