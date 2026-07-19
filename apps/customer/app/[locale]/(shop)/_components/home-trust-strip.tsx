/**
 * Compact post-hero trust strip for the customer homepage (CUST-HOME-01).
 * Escrow copy must stay payment-gated honest — no “MoMo/card live” claims.
 */

export type HomeTrustStripLabels = {
  ariaLabel: string;
  sellers: string;
  fulfillment: string;
  returns: string;
  escrow: string;
};

type HomeTrustStripProps = {
  labels: HomeTrustStripLabels;
};

const ITEMS: Array<{ key: keyof Omit<HomeTrustStripLabels, "ariaLabel">; testId: string }> = [
  { key: "sellers", testId: "home-trust-sellers" },
  { key: "fulfillment", testId: "home-trust-fulfillment" },
  { key: "returns", testId: "home-trust-returns" },
  { key: "escrow", testId: "home-trust-escrow" },
];

export function HomeTrustStrip({ labels }: HomeTrustStripProps) {
  return (
    <section
      data-testid="home-trust-strip"
      aria-label={labels.ariaLabel}
      className="rounded-lg border border-border bg-bg-2/70 px-3 py-3"
    >
      <ul className="m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-4 lg:gap-3">
        {ITEMS.map((item) => (
          <li
            key={item.key}
            data-testid={item.testId}
            className="flex min-h-11 items-start gap-2 text-sm text-text-2"
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
