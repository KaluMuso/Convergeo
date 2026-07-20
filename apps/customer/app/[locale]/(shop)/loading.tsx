import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Shop-route loading shell — skeleton-to-content path for homepage and nested
 * shop pages. Honours prefers-reduced-motion via Skeleton / base.css shimmer.
 */
export default function ShopLoading() {
  return (
    <div data-testid="shop-loading" className="flex flex-col gap-6 lg:gap-10" aria-busy="true">
      <div className="motion-fade -mx-4 aspect-[16/9] overflow-hidden bg-bg-2 lg:-mx-6 lg:aspect-[21/9]">
        <Skeleton shape="block" className="h-full w-full" />
      </div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} shape="block" className="h-14 w-full rounded" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} shape="block" className="aspect-square w-full rounded-lg" />
        ))}
      </div>
      <div className="motion-stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} shape="block" className="aspect-[3/4] w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}
