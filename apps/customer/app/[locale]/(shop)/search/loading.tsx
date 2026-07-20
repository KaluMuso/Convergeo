import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Search route skeleton (App Router `loading.tsx`). Renders instantly while the
 * server component resolves the `/search` + tab-count requests, so 3G loads feel
 * responsive. Purely presentational — every Skeleton is aria-hidden, no strings.
 */
export default function SearchLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl py-4 motion-fade sm:py-6" aria-hidden="true">
      <header className="mb-4 space-y-3">
        <Skeleton shape="line" width="9rem" height="1.6rem" />
        <Skeleton height="2.75rem" />
      </header>

      <div className="mb-6 flex gap-2 motion-stagger">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} shape="line" width="4.5rem" height="2rem" />
        ))}
      </div>

      <div className="flex flex-col gap-3 motion-stagger">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex gap-3 rounded border border-border p-3">
            <Skeleton width="4.5rem" height="4.5rem" />
            <div className="flex flex-1 flex-col gap-2 py-1">
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
