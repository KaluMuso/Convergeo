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
 * every card opens a real page.
 */
export function CitationCard({ citation, locale, viewLabel, meta = null }: CitationCardProps) {
  const href = searchResultHref(locale, citation);

  return (
    <Link
      href={href}
      aria-label={`${viewLabel}: ${citation.title}`}
      data-testid="ask-citation-card"
      data-kind={kindOf(citation.entity_kind)}
      className="flex min-h-16 flex-col justify-center gap-1 rounded-lg border border-border bg-surface p-3 text-left hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span className="line-clamp-2 text-sm font-medium text-text">{citation.title}</span>
      {citation.price_display ? (
        <span className="text-sm font-semibold text-primary">{citation.price_display}</span>
      ) : null}
      {meta ? <span className="text-xs text-text-3">{meta}</span> : null}
    </Link>
  );
}
