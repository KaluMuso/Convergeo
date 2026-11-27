import { Skeleton } from "@vergeo/ui/src/skeleton";

/** Route skeleton: tab strip + tree rows while the page chunk and permissions resolve. */
export default function Loading() {
  return (
    <div className="space-y-4" data-testid="admin-categories-loading" aria-busy="true">
      <Skeleton shape="line" width="12rem" height="2rem" />
      <div className="flex gap-2">
        {[0, 1, 2, 3].map((key) => (
          <Skeleton key={key} shape="block" width="6rem" height="2.75rem" />
        ))}
      </div>
      {[0, 1, 2, 3, 4].map((key) => (
        <Skeleton key={key} shape="block" height="4.5rem" />
      ))}
    </div>
  );
}
