import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Inline skeleton for search results Suspense fallback (filters + grid).
 */
export function SearchResultsSkeleton() {
  return (
    <div
      className="flex min-w-0 flex-col gap-3"
      data-testid="search-results-loading"
      aria-busy="true"
      aria-hidden="true"
    >
      <div className="mb-3 flex gap-2 motion-stagger">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={index} shape="line" width="4.5rem" height="2rem" />
        ))}
      </div>
      <Skeleton shape="line" width="8rem" height="1rem" />
      <div className="grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="rounded border border-border p-2">
            <Skeleton shape="block" className="aspect-[4/3] w-full rounded" />
            <div className="flex flex-col gap-2 py-2">
              <Skeleton shape="line" width="80%" />
              <Skeleton shape="line" width="50%" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
