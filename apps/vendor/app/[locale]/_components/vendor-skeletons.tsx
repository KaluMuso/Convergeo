import { Skeleton } from "@vergeo/ui/src/skeleton";

/**
 * Layout-shaped loading placeholders (no layout jump when data lands on 3G).
 * The shimmer itself is aria-hidden; each skeleton carries one sr-only status
 * line with an already-localised label.
 */
type SkeletonProps = {
  label: string;
};

function LoadingLabel({ label }: SkeletonProps) {
  return (
    <p className="sr-only" role="status">
      {label}
    </p>
  );
}

function CardRow() {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-3">
      <Skeleton shape="line" width="60%" />
      <Skeleton shape="line" width="35%" />
      <Skeleton shape="line" width="25%" />
    </div>
  );
}

export function ListSkeleton({ label, rows = 3 }: SkeletonProps & { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" data-testid="vendor-list-skeleton">
      <LoadingLabel label={label} />
      <Skeleton shape="line" width="40%" height="1.25rem" />
      <Skeleton shape="line" width="80%" />
      {Array.from({ length: rows }, (_, index) => (
        <CardRow key={index} />
      ))}
    </div>
  );
}

export function DashboardSkeleton({ label }: SkeletonProps) {
  return (
    <div className="flex flex-col gap-5 pb-8" data-testid="vendor-dashboard-skeleton">
      <LoadingLabel label={label} />
      <div className="flex flex-col gap-2 px-1">
        <Skeleton shape="line" width="30%" />
        <Skeleton shape="line" width="50%" height="1.5rem" />
      </div>
      <Skeleton shape="block" height="4.5rem" />
      <div className="flex flex-col gap-3">
        <CardRow />
        <CardRow />
        <CardRow />
      </div>
      <Skeleton shape="block" height="6rem" />
    </div>
  );
}

export function OrderDetailSkeleton({ label }: SkeletonProps) {
  return (
    <div className="flex flex-col gap-5 pb-8" data-testid="vendor-order-skeleton">
      <LoadingLabel label={label} />
      <div className="flex flex-col gap-2">
        <Skeleton shape="line" width="20%" />
        <Skeleton shape="line" width="45%" height="1.5rem" />
      </div>
      <Skeleton shape="block" height="7rem" />
      <Skeleton shape="block" height="4rem" />
      <CardRow />
      <Skeleton shape="block" height="10rem" />
    </div>
  );
}
