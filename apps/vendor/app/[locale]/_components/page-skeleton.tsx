import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Streaming placeholder for vendor pages whose data loads on the client. Shown by
 * route `loading.tsx` files (instant, during navigation) and by the client views
 * while their first fetch is in flight, so the page shell never sits blank.
 */
export function VendorPageSkeleton({
  rows = 3,
  label,
}: {
  rows?: number;
  /** Accessible loading label; the blocks themselves are decorative. */
  label?: string;
}) {
  return (
    <div
      className="flex w-full flex-col gap-4"
      role="status"
      aria-busy="true"
      aria-label={label}
      data-testid="vendor-page-skeleton"
    >
      <Skeleton shape="line" width="40%" height="1.75rem" />
      <Skeleton shape="line" width="70%" />
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} shape="block" height="6rem" />
      ))}
    </div>
  );
}
