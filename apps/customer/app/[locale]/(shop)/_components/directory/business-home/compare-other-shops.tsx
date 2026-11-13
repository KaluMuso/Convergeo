import Link from "next/link";

/** Per-listing compare action, pre-labelled on the server (ICU plural there). */
export type StorefrontCompare = {
  href: string;
  label: string;
  ariaLabel: string;
};

/**
 * Builds the "Compare with N other shops · from K…" action for a canonical
 * listing. Returns null when no other shop sells the same product — a link to a
 * one-row comparison would waste a 3G round trip.
 */
export function buildStorefrontCompare(input: {
  locale: string;
  productSlug: string | null;
  title: string;
  otherOffersCount: number;
  otherMinPriceNgwee: number | null;
  labels: {
    count: (count: number) => string;
    from: (priceNgwee: number) => string;
    aria: (title: string) => string;
  };
}): StorefrontCompare | null {
  if (!input.productSlug || input.otherOffersCount < 1) {
    return null;
  }
  const countLabel = input.labels.count(input.otherOffersCount);
  const label =
    input.otherMinPriceNgwee !== null
      ? `${countLabel} · ${input.labels.from(input.otherMinPriceNgwee)}`
      : countLabel;
  return {
    // `#compare` lands on the PDP's canonical-product comparison (all shops,
    // price, distance/delivery and rating) — the same item, never a dead end.
    href: `/${input.locale}/p/${encodeURIComponent(input.productSlug)}#compare`,
    label,
    ariaLabel: input.labels.aria(input.title),
  };
}

export function CompareOtherShopsLink({ compare }: { compare: StorefrontCompare }) {
  return (
    <Link
      href={compare.href}
      aria-label={`${compare.ariaLabel} — ${compare.label}`}
      data-testid="storefront-compare"
      className="inline-flex min-h-11 w-full items-center gap-1.5 rounded border border-border bg-surface px-2.5 text-xs font-semibold text-primary no-underline hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="h-4 w-4 shrink-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M7 7h13M17 4l3 3-3 3M17 17H4M7 14l-3 3 3 3" />
      </svg>
      <span className="min-w-0 leading-tight">{compare.label}</span>
    </Link>
  );
}
