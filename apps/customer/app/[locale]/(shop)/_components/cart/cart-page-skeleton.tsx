import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Cart page skeleton — shared by route `loading.tsx` and client-side cart fetch.
 * Presentational only (aria-hidden visuals + optional sr-only status).
 */
export function CartPageSkeleton({ loadingLabel }: { loadingLabel?: string }) {
  return (
    <div data-testid="cart-loading" aria-busy="true">
      {loadingLabel ? (
        <p className="sr-only" aria-live="polite">
          {loadingLabel}
        </p>
      ) : null}
      <div className="flex flex-col gap-3 motion-stagger" aria-hidden="true">
        <Skeleton shape="line" width="12rem" height="1.75rem" />
        {[0, 1].map((groupIndex) => (
          <section key={groupIndex} className="flex flex-col gap-3">
            <Skeleton shape="line" width="10rem" />
            <Skeleton height="4rem" />
            {[0, 1].map((lineIndex) => (
              <div key={lineIndex} className="flex gap-3">
                <Skeleton width="4rem" height="4rem" />
                <div className="flex flex-1 flex-col gap-2 py-1">
                  <Skeleton shape="line" width="75%" />
                  <Skeleton shape="line" width="40%" />
                </div>
              </div>
            ))}
          </section>
        ))}
        <aside className="flex flex-col gap-3 rounded-lg border border-border p-4 lg:hidden">
          <Skeleton shape="line" width="8rem" height="1.25rem" />
          <Skeleton height="2.5rem" />
          <Skeleton height="3rem" />
        </aside>
      </div>
    </div>
  );
}
