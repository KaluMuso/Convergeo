"use client";

import { Badge } from "../_lib/ui";

import type { CommissionPreview } from "../_lib/types";

type CommissionBannerProps = {
  commission: CommissionPreview;
  categoryName?: string;
  labels: {
    heading: string;
    body: string;
    rate: string;
  };
};

export function CommissionBanner({ commission, categoryName, labels }: CommissionBannerProps) {
  const rateLabel = labels.rate.replace("{rate}", String(commission.rate_percent));

  return (
    <aside
      className="rounded-lg border border-primary/20 bg-primary-tint p-3"
      aria-label={labels.heading}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="text-sm font-medium text-text">{labels.heading}</p>
          <p className="text-sm text-text-2">{labels.body}</p>
          {categoryName ? <p className="text-xs text-text-3">{categoryName}</p> : null}
        </div>
        <Badge variant="new" label={rateLabel} />
      </div>
    </aside>
  );
}
