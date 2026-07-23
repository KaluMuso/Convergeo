import { LinkButton } from "@vergeo/ui/src/link-button";
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
      <LinkButton
        href={browseHref}
        data-testid="pdp-no-sellers-browse"
        variant="primary"
        className="w-fit rounded-lg text-sm"
        LinkComponent={Link}
      >
        {browseLabel}
      </LinkButton>
    </section>
  );
}
