import Link from "next/link";

export type NoSellersPanelProps = {
  title: string;
  body: string;
  browseLabel: string;
  browseHref: string;
};

/**
 * Honest zero-offer state. Never invents a seller or a fake “add to cart”.
 */
export function NoSellersPanel({ title, body, browseLabel, browseHref }: NoSellersPanelProps) {
  return (
    <section
      data-testid="pdp-no-sellers"
      className="flex flex-col gap-3 rounded border border-border bg-surface p-5"
      style={{ borderRadius: "var(--r)" }}
      aria-live="polite"
    >
      <h2 className="font-display text-lg font-semibold text-text">{title}</h2>
      <p className="text-sm leading-relaxed text-text-2">{body}</p>
      <Link
        href={browseHref}
        data-testid="pdp-no-sellers-browse"
        className="inline-flex min-h-11 w-fit items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-[var(--primary-btn-fg)] focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {browseLabel}
      </Link>
    </section>
  );
}
