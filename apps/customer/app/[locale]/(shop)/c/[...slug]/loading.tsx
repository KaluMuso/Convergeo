import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Category / PLP route skeleton (App Router `loading.tsx`). Mirrors the facet
 * sidebar + product grid while the catalog request resolves. Presentational only
 * (aria-hidden, no user-facing strings).
 */
export default function PlpLoading() {
  return (
    <div
      className="mx-auto flex w-full max-w-6xl flex-col gap-4 py-4 motion-fade"
      aria-hidden="true"
    >
      <header className="flex flex-col gap-2">
        <Skeleton shape="line" width="12rem" height="1.75rem" />
        <Skeleton shape="line" width="7rem" />
      </header>

      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="hidden flex-col gap-3 lg:flex">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex flex-col gap-2 rounded border border-border p-3">
              <Skeleton shape="line" width="60%" />
              <Skeleton shape="line" width="90%" height="1.1rem" />
              <Skeleton shape="line" width="80%" height="1.1rem" />
            </div>
          ))}
        </aside>

        <section className="grid grid-cols-2 gap-3 motion-stagger sm:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="flex flex-col gap-2 rounded border border-border p-2">
              <Skeleton height="8rem" />
              <Skeleton shape="line" width="85%" />
              <Skeleton shape="line" width="55%" />
              <Skeleton shape="line" width="40%" height="1.05rem" />
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
