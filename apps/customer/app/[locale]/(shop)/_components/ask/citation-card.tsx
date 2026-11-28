import Link from "next/link";

import { searchResultHref } from "../search/search-result-href";

import type { AskCitation } from "./types";

export type CitationCardProps = {
  citation: AskCitation;
  locale: string;
  /** Localised aria-label for the deep-link (e.g. "View product"). */
  viewLabel: string;
  /** Optional resolved badge text (e.g. "In stock", "1.2 km away"). */
  meta?: string | null;
  /** Localised "Sold by {vendor}" text for the seller link (omit when no seller known). */
  vendorLabel?: string | null;
};

function kindOf(entityKind: string): "event" | "vendor" | "service" | "product" {
  if (entityKind === "event" || entityKind === "vendor" || entityKind === "service") {
    return entityKind;
  }
  return "product";
}

/**
 * Lightweight citation card. `CitationRef` only carries
 * `{ entity_kind, entity_id, title, price_display, slug }`, so we render exactly those
 * fields rather than the full ProductCard/EventCard (which require ngwee/rating we
 * do not have — fabricating them would violate the money-integrity rule).
 * Deep-links via the shared `searchResultHref` (slug-based, never `/p/{uuid}`), so
 * every card opens a real page. When the API resolved the seller, a second link opens
 * the vendor page (a sibling anchor, never nested inside the item link).
 */
export function CitationCard({
  citation,
  locale,
  viewLabel,
  meta = null,
  vendorLabel = null,
}: CitationCardProps) {
  const href = searchResultHref(locale, citation);
  const vendorSlug = citation.vendor_slug?.trim() || null;
  // The vendor card already *is* the vendor page; a second link would only repeat it.
  const showVendorLink =
    Boolean(vendorLabel) && vendorSlug !== null && citation.entity_kind !== "vendor";
  const vendorHref = vendorSlug
    ? searchResultHref(locale, {
        entity_kind: "vendor",
        entity_id: citation.vendor_id ?? citation.entity_id,
        title: citation.vendor_name ?? citation.title,
        slug: vendorSlug,
      })
    : null;

  return (
    <div
      data-testid="ask-citation"
      className="flex flex-col rounded-lg border border-border bg-surface hover:border-primary"
    >
      <Link
        href={href}
        aria-label={`${viewLabel}: ${citation.title}`}
        data-testid="ask-citation-card"
        data-kind={kindOf(citation.entity_kind)}
        className="flex min-h-16 flex-col justify-center gap-1 rounded-lg p-3 text-left focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        <span className="line-clamp-2 text-sm font-medium text-text">{citation.title}</span>
        {citation.price_display ? (
          <span className="text-sm font-semibold text-primary">{citation.price_display}</span>
        ) : null}
        {meta ? <span className="text-xs text-text-3">{meta}</span> : null}
      </Link>
      {showVendorLink && vendorHref ? (
        <Link
          href={vendorHref}
          data-testid="ask-citation-vendor"
          className="inline-flex min-h-11 items-center rounded-b-lg border-t border-border px-3 text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {vendorLabel}
        </Link>
      ) : null}
    </div>
  );
}
