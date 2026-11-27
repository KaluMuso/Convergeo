import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Route-segment fallback: shown while the next page's client chunk downloads, so a
 * navigation paints chrome-matching skeletons instead of freezing on the old page.
 * Decorative only (aria-hidden); the shell keeps its own permission status text.
 */
export default function AdminRouteLoading() {
  return (
    <div
      aria-hidden="true"
      className="mx-auto w-full max-w-7xl space-y-4"
      data-testid="admin-route-loading"
    >
      <Skeleton shape="line" height="1.75rem" width="30%" />
      <Skeleton shape="line" height="0.75rem" width="50%" />
      <Skeleton shape="block" height="3rem" />
      <Skeleton shape="block" height="3rem" />
      <Skeleton shape="block" height="3rem" />
    </div>
  );
}
