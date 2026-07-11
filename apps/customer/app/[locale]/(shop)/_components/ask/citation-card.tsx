import Link from "next/link";

import type { AskCitation } from "./types";

export type CitationCardProps = {
  citation: AskCitation;
  locale: string;
  /** Localised aria-label for the deep-link (e.g. "View product"). */
  viewLabel: string;
};

/**
 * Lightweight citation card. `CitationRef` only carries
 * `{ entity_kind, entity_id, title, price_display }`, so we render exactly those
 * fields rather than the full ProductCard/EventCard (which require ngwee/rating we
 * do not have — fabricating them would violate the money-integrity rule).
 * Deep-links by `entity_id`, matching the search results href convention.
 */
export function CitationCard({ citation, locale, viewLabel }: CitationCardProps) {
  const isEvent = citation.entity_kind === "event";
  const routeSegment = isEvent ? "e" : "p";
  const href = `/${locale}/${routeSegment}/${encodeURIComponent(citation.entity_id)}`;

  return (
    <Link
      href={href}
      aria-label={`${viewLabel}: ${citation.title}`}
      data-testid="ask-citation-card"
      data-kind={isEvent ? "event" : "product"}
      className="flex min-h-16 flex-col justify-center gap-1 rounded-lg border border-border bg-surface p-3 text-left hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <span className="line-clamp-2 text-sm font-medium text-text">{citation.title}</span>
      {citation.price_display ? (
        <span className="text-sm font-semibold text-primary">{citation.price_display}</span>
      ) : null}
    </Link>
  );
}
