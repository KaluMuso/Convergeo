import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Below-the-fold reviews panel skeleton for PDP Suspense boundary.
 */
export function ReviewsSkeleton() {
  return (
    <div
      className="flex flex-col gap-4 py-4"
      data-testid="pdp-reviews-loading"
      aria-busy="true"
      aria-hidden="true"
    >
      <Skeleton shape="line" width="10rem" height="1.25rem" />
      <div className="flex flex-col gap-3 motion-stagger">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="flex flex-col gap-2 rounded border border-border p-3">
            <Skeleton shape="line" width="6rem" />
            <Skeleton shape="line" width="90%" />
            <Skeleton shape="line" width="70%" />
          </div>
        ))}
      </div>
    </div>
  );
}
