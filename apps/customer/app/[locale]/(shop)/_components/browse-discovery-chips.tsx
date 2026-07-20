import Link from "next/link";

export type BrowseDiscoveryChip = {
  key: string;
  href: string;
  label: string;
};

type BrowseDiscoveryChipsProps = {
  chips: BrowseDiscoveryChip[];
  ariaLabel: string;
};

/**
 * Browse entry chips shown on the search hub (audit §5.3): Categories · Directory ·
 * Services · Events. Real routes only — no mock destinations.
 */
export function BrowseDiscoveryChips({ chips, ariaLabel }: BrowseDiscoveryChipsProps) {
  if (chips.length === 0) {
    return null;
  }

  return (
    <nav data-testid="browse-discovery-chips" aria-label={ariaLabel} className="mb-4">
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {chips.map((chip) => (
          <li key={chip.key}>
            <Link
              href={chip.href}
              className="inline-flex min-h-11 items-center rounded border border-border bg-surface px-3 text-sm font-medium text-text-2 transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {chip.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
