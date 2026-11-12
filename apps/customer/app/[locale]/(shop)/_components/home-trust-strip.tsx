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

/** 24px stroke glyphs — inline so the strip costs no icon-pack bytes. */
const ICON_PATHS: Record<(typeof ITEMS)[number]["key"], string> = {
  sellers: "M12 3 4.5 6v5.5c0 4.4 3.1 8.2 7.5 9.5 4.4-1.3 7.5-5.1 7.5-9.5V6L12 3Zm-3 9 2 2 4-4.5",
  fulfillment:
    "M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm10 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
  returns: "M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4",
  escrow: "M6 10V8a6 6 0 1 1 12 0v2M5 10h14v10H5zM12 14v2.5",
};

export function HomeTrustStrip({ labels }: HomeTrustStripProps) {
  const escrowSteps = [labels.escrowStep1, labels.escrowStep2, labels.escrowStep3];

  return (
    <section
      data-testid="home-trust-strip"
      aria-label={labels.ariaLabel}
      className="grid gap-4 rounded-lg border border-border bg-surface p-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-8 lg:p-6"
    >
      {/* The escrow promise is a real sequence, so it reads as an ordered track. */}
      <ol
        data-testid="home-trust-escrow-ladder"
        className="m-0 grid list-none grid-cols-3 gap-2 rounded bg-primary-tint p-3 text-primary-deep"
      >
        {escrowSteps.map((step, index) => (
          <li
            key={`escrow-step-${index}`}
            className="relative flex flex-col items-start gap-2 text-sm font-semibold leading-snug"
          >
            <span className="flex w-full items-center gap-1.5" aria-hidden>
              <span
                className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-display text-sm ${
                  index === 1
                    ? "bg-primary text-surface ring-2 ring-accent"
                    : "bg-surface text-primary"
                }`}
              >
                {index + 1}
              </span>
              {index < escrowSteps.length - 1 ? (
                <span className="h-0.5 flex-1 rounded-full bg-primary/25" />
              ) : null}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      <ul className="m-0 grid list-none grid-cols-2 gap-x-4 gap-y-3 p-0 lg:grid-cols-4">
        {ITEMS.map((item) => (
          <li
            key={item.key}
            data-testid={item.testId}
            className="flex items-start gap-2.5 text-sm leading-snug text-text-2"
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              className="mt-px h-5 w-5 shrink-0 text-primary"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d={ICON_PATHS[item.key]} />
            </svg>
            <span>{labels[item.key]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
