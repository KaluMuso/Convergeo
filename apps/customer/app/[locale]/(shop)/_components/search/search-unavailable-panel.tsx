import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

import { BrowseDiscoveryChips, type BrowseDiscoveryChip } from "../browse-discovery-chips";

export type SearchUnavailablePanelLabels = {
  title: string;
  body: string;
  retry: string;
  browseHeading: string;
};

type SearchUnavailablePanelProps = {
  retryHref: string;
  labels: SearchUnavailablePanelLabels;
  chips: BrowseDiscoveryChip[];
  browseAriaLabel: string;
};

/** Search API failure — retry plus browse fallbacks (audit §4.2). */
export function SearchUnavailablePanel({
  retryHref,
  labels,
  chips,
  browseAriaLabel,
}: SearchUnavailablePanelProps) {
  return (
    <div className="space-y-4" data-testid="search-unavailable">
      <EmptyState
        title={labels.title}
        body={labels.body}
        action={
          <LinkButton
            href={retryHref}
            variant="primary"
            className="rounded-lg text-sm"
            LinkComponent={Link}
          >
            {labels.retry}
          </LinkButton>
        }
      />
      <section aria-labelledby="search-unavailable-browse">
        <h2 id="search-unavailable-browse" className="mb-2 text-sm font-semibold text-text">
          {labels.browseHeading}
        </h2>
        <BrowseDiscoveryChips ariaLabel={browseAriaLabel} chips={chips} />
      </section>
    </div>
  );
}
