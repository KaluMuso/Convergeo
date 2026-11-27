import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Streaming fallback for a below-the-fold home rail section. Fixed rail height
 * keeps layout shift low when the real rails arrive. Presentational only.
 */
export function HomeRailFallback({ testId, rows = 1 }: { testId: string; rows?: number }) {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true" data-testid={testId}>
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex flex-col gap-2">
          <Skeleton shape="line" width="40%" height="1.25rem" />
          <div className="flex gap-2 overflow-hidden">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} shape="block" className="aspect-[3/4] w-40 shrink-0 rounded-lg" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
