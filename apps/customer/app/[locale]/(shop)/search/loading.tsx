import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Search route skeleton (App Router `loading.tsx`). Renders instantly while the
 * server component resolves the `/search` + tab-count requests, so 3G loads feel
 * responsive. Purely presentational — every Skeleton is aria-hidden, no strings.
 */
export default function SearchLoading() {
  return (
    <div
      className="mx-auto w-full max-w-3xl py-3 motion-fade sm:py-5 lg:max-w-6xl xl:max-w-7xl"
      aria-hidden="true"
    >
      <header className="mb-3 space-y-3 lg:mb-4">
        <Skeleton shape="line" width="9rem" height="1.6rem" />
        <Skeleton height="2.75rem" />
      </header>

      <div className="mb-6 flex gap-2 motion-stagger">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} shape="line" width="4.5rem" height="2rem" />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2 motion-stagger sm:gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded border border-border p-2">
            <Skeleton shape="block" className="aspect-[4/3] w-full rounded" />
            <div className="flex flex-1 flex-col gap-2 py-2">
              <Skeleton shape="line" width="80%" />
              <Skeleton shape="line" width="50%" />
              <Skeleton shape="line" width="30%" height="1.05rem" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
