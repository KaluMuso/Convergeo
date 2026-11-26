import { Skeleton } from "@vergeo/ui/src/skeleton";

export default function AccountLoading() {
  return (
    <div className="space-y-4" data-testid="account-loading" aria-busy="true">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} shape="block" className="h-24 w-full rounded border border-border" />
      ))}
    </div>
  );
}
