"use client";

import { Button } from "@vergeo/ui/src/button";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";

import { useRecentlyViewed } from "../../../(shop)/_components/recently-viewed/use-recently-viewed";

export type RecentlyViewedPanelLabels = {
  title: string;
  description: string;
  privacyNote: string;
  emptyTitle: string;
  emptyBody: string;
  browseCta: string;
  clear: string;
  clearing: string;
  loading: string;
  remove: string;
  removeLabel: string;
  viewProduct: string;
};

type Props = {
  locale: string;
  labels: RecentlyViewedPanelLabels;
};

export function RecentlyViewedPanel({ locale, labels }: Props) {
  const { entries, hydrated, clear, remove } = useRecentlyViewed();

  return (
    <section className="space-y-4" data-testid="recently-viewed-panel">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="text-sm text-text-2">{labels.description}</p>
        <p className="text-xs text-text-3">{labels.privacyNote}</p>
      </header>

      {!hydrated ? (
        <p className="text-sm text-text-3" aria-live="polite">
          {labels.loading}
        </p>
      ) : null}

      {hydrated && entries.length === 0 ? (
        <EmptyState
          title={labels.emptyTitle}
          body={labels.emptyBody}
          data-testid="recently-viewed-empty"
          action={
            <LinkButton
              href={`/${locale}`}
              variant="primary"
              className="text-sm"
              LinkComponent={Link}
            >
              {labels.browseCta}
            </LinkButton>
          }
        />
      ) : null}

      {hydrated && entries.length > 0 ? (
        <>
          <div className="flex justify-end">
            <Button
              type="button"
              variant="secondary"
              size="md"
              loading={false}
              loadingLabel={labels.clearing}
              data-testid="recently-viewed-clear"
              onClick={() => clear()}
            >
              {labels.clear}
            </Button>
          </div>
          <ul className="space-y-2" data-testid="recently-viewed-list">
            {entries.map((entry) => (
              <li
                key={`${entry.slug}-${entry.viewedAt}`}
                className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <Link
                  href={`/${locale}/p/${entry.slug}`}
                  className="min-w-0 break-words font-medium text-display-ink underline-offset-2 hover:underline"
                >
                  {entry.name}
                </Link>
                <div className="flex flex-wrap gap-2">
                  <LinkButton
                    href={`/${locale}/p/${entry.slug}`}
                    variant="secondary"
                    className="px-3 text-sm"
                    LinkComponent={Link}
                  >
                    {labels.viewProduct}
                  </LinkButton>
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center rounded border border-border px-3 text-sm font-medium text-text"
                    aria-label={labels.removeLabel.replace("{name}", entry.name)}
                    onClick={() => remove(entry.slug)}
                  >
                    {labels.remove}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
