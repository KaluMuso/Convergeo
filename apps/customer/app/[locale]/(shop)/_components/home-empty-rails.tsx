import { LinkButton } from "@vergeo/ui/src/link-button";
import { SpotIllustration } from "@vergeo/ui/src/spot-illustrations";
import Link from "next/link";

export type HomeEmptyRailsLabels = {
  title: string;
  body: string;
  browse: string;
  sell: string;
};

const GHOST_RAILS = ["a", "b"] as const;
const GHOST_CARDS = [0, 1, 2, 3, 4, 5] as const;

function ghostCardVisibility(index: number): string {
  if (index >= 4) return "hidden lg:flex";
  if (index >= 3) return "hidden sm:flex";
  return "flex";
}

function GhostCard({ index }: { index: number }) {
  return (
    <div
      className={`${ghostCardVisibility(index)} flex-col gap-2 rounded-lg border border-border bg-surface p-2`}
    >
      <div className="aspect-square w-full rounded bg-bg-2" />
      <div className="h-3 w-4/5 rounded-sm bg-bg-2" />
      <div className="h-3 w-2/5 rounded-sm bg-bg-2" />
    </div>
  );
}

/**
 * Shown below the hero when the API returned no rails, deals or stream items,
 * so the home page never ends in blank space. The ghost rails are decorative.
 */
export function HomeEmptyRails({
  locale,
  labels,
}: {
  locale: string;
  labels: HomeEmptyRailsLabels;
}) {
  return (
    <section
      aria-labelledby="home-empty-rails-title"
      className="home-rail flex flex-col gap-6"
      data-testid="home-empty-rails"
    >
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-2 text-center">
        <div aria-hidden="true" className="w-28 text-primary">
          <SpotIllustration id="no-products" className="h-auto w-full" />
        </div>
        <h2
          id="home-empty-rails-title"
          className="m-0 font-display text-h3 font-bold text-display-ink"
        >
          {labels.title}
        </h2>
        <p className="m-0 text-sm text-text-2">{labels.body}</p>
        <div className="mt-1 flex flex-wrap justify-center gap-2">
          <LinkButton href={`/${locale}/search`} variant="primary" LinkComponent={Link}>
            {labels.browse}
          </LinkButton>
          <LinkButton href={`/${locale}/sell`} variant="secondary" LinkComponent={Link}>
            {labels.sell}
          </LinkButton>
        </div>
      </div>
      <div
        aria-hidden="true"
        className="flex flex-col gap-6 [mask-image:linear-gradient(to_bottom,black_40%,transparent)]"
      >
        {GHOST_RAILS.map((rail) => (
          <div key={rail} className="flex flex-col gap-3" data-testid="home-empty-ghost-rail">
            <div className="h-5 w-40 rounded-sm bg-bg-2" />
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {GHOST_CARDS.map((card) => (
                <GhostCard key={card} index={card} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
