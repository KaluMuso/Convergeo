import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Product detail (PDP) route skeleton. Matches mobile hierarchy:
 * breadcrumbs → title → gallery → buy box (audit §4.4).
 * Presentational only (aria-hidden, no user-facing strings).
 */
export default function PdpLoading() {
  return (
    <main
      className="mx-auto flex w-full max-w-lg flex-col gap-6 px-4 py-6 motion-fade lg:max-w-6xl"
      aria-hidden="true"
      data-testid="pdp-loading"
    >
      <Skeleton shape="line" width="40%" height="0.9rem" />

      <header className="flex flex-col gap-2">
        <Skeleton shape="line" width="25%" height="1rem" />
        <Skeleton shape="line" width="85%" height="1.6rem" />
        <Skeleton shape="line" width="35%" height="1rem" />
      </header>

      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] lg:gap-8">
        <Skeleton height="18rem" className="w-full" />
        <div className="flex flex-col gap-3">
          <Skeleton height="3rem" />
          <Skeleton height="2.5rem" />
          <Skeleton height="3rem" />
        </div>
      </div>

      <div className="flex flex-col gap-2 motion-stagger">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex justify-between gap-4">
            <Skeleton shape="line" width="35%" />
            <Skeleton shape="line" width="45%" />
          </div>
        ))}
      </div>
    </main>
  );
}
