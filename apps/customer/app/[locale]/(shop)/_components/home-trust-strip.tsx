/**
 * Slim post-hero trust strip for the customer homepage. COD-only pilot:
 * copy never mentions escrow, mobile money or cards (see docs/plan decisions).
 * Server component, inline glyphs, no client JS.
 */

export type HomeTrustStripLabels = {
  ariaLabel: string;
  cod: string;
  verified: string;
  lusaka: string;
  returns: string;
};

type HomeTrustStripProps = {
  labels: HomeTrustStripLabels;
};

type TrustKey = keyof Omit<HomeTrustStripLabels, "ariaLabel">;

const ITEMS: Array<{ key: TrustKey; testId: string; path: string }> = [
  {
    key: "cod",
    testId: "home-trust-cod",
    path: "M3 7h18v10H3zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM6.5 10v4M17.5 10v4",
  },
  {
    key: "verified",
    testId: "home-trust-verified",
    path: "M12 3 4.5 6v5.5c0 4.4 3.1 8.2 7.5 9.5 4.4-1.3 7.5-5.1 7.5-9.5V6L12 3Zm-3 9 2 2 4-4.5",
  },
  {
    key: "lusaka",
    testId: "home-trust-lusaka",
    path: "M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm10 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
  },
  {
    key: "returns",
    testId: "home-trust-returns",
    path: "M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4",
  },
];

export function HomeTrustStrip({ labels }: HomeTrustStripProps) {
  return (
    <section
      data-testid="home-trust-strip"
      aria-label={labels.ariaLabel}
      className="rounded-lg border border-border bg-surface px-2 py-1.5"
    >
      <ul className="m-0 grid list-none grid-cols-2 gap-x-2 gap-y-1 p-0 sm:grid-cols-4">
        {ITEMS.map((item) => (
          <li
            key={item.key}
            data-testid={item.testId}
            className="flex min-h-8 items-center gap-1.5 text-xs font-medium leading-tight text-text-2 sm:justify-center"
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              className="h-4 w-4 shrink-0 text-primary"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d={item.path} />
            </svg>
            <span>{labels[item.key]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
