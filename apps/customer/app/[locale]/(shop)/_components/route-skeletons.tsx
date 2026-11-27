import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Route-shaped loading skeletons shared by the shop `loading.tsx` files, so a
 * list/detail route streams a placeholder that matches its own layout instead
 * of inheriting the home-shaped shell (less layout shift when content arrives).
 * Presentational only: aria-hidden, no user-facing strings.
 */
export function ListRouteSkeleton({
  testId,
  cards = 8,
  filters = true,
}: {
  testId: string;
  cards?: number;
  filters?: boolean;
}) {
  return (
    <div className="motion-fade flex flex-col gap-4 py-4" aria-hidden="true" data-testid={testId}>
      <Skeleton shape="line" width="55%" height="1.6rem" />
      {filters ? (
        <div className="flex gap-2 overflow-hidden">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton
              key={i}
              shape="block"
              width="5.5rem"
              height="2.25rem"
              className="shrink-0 rounded-full"
            />
          ))}
        </div>
      ) : null}
      <div className="motion-stagger grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: cards }, (_, i) => (
          <Skeleton key={i} shape="block" className="aspect-[3/4] w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}

export function DetailRouteSkeleton({ testId }: { testId: string }) {
  return (
    <div
      className="motion-fade mx-auto flex w-full max-w-lg flex-col gap-5 py-4 lg:max-w-5xl"
      aria-hidden="true"
      data-testid={testId}
    >
      <Skeleton shape="line" width="40%" height="0.9rem" />
      <div className="flex flex-col gap-5 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:gap-8">
        <Skeleton height="16rem" className="aspect-[4/3] w-full" />
        <div className="flex flex-col gap-3">
          <Skeleton shape="line" width="80%" height="1.5rem" />
          <Skeleton shape="line" width="40%" height="1rem" />
          <Skeleton height="3rem" />
          <Skeleton height="2.75rem" />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} shape="line" width={`${90 - i * 12}%`} />
        ))}
      </div>
    </div>
  );
}

export function FormRouteSkeleton({ testId }: { testId: string }) {
  return (
    <div
      className="motion-fade mx-auto flex w-full max-w-2xl flex-col gap-4 py-4"
      aria-hidden="true"
      data-testid={testId}
    >
      <Skeleton shape="line" width="45%" height="1.6rem" />
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} shape="block" height="5.5rem" className="w-full rounded-lg" />
      ))}
      <Skeleton shape="block" height="3rem" className="w-full rounded-lg" />
    </div>
  );
}
