import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Product detail (PDP) route skeleton (App Router `loading.tsx`). Holds the gallery
 * + price + CTA shape while the product / comparison request resolves.
 * Presentational only (aria-hidden, no user-facing strings).
 */
export default function PdpLoading() {
  return (
    <main
      className="mx-auto flex w-full max-w-lg flex-col gap-6 px-4 py-6 motion-fade lg:max-w-6xl"
      aria-hidden="true"
    >
      <Skeleton height="18rem" />

      <header className="flex flex-col gap-2">
        <Skeleton shape="line" width="30%" height="1rem" />
        <Skeleton shape="line" width="85%" height="1.6rem" />
        <Skeleton shape="line" width="70%" height="1.6rem" />
      </header>

      <Skeleton shape="line" width="8rem" height="1.6rem" />

      <div className="flex flex-col gap-3">
        <Skeleton height="3rem" />
        <Skeleton height="3rem" />
      </div>

      <div className="flex flex-col gap-2 motion-stagger">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex justify-between gap-4">
            <Skeleton shape="line" width="35%" />
            <Skeleton shape="line" width="45%" />
          </div>
        ))}
      </div>
    </main>
  );
}
