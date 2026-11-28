"use client";

import { StatusChip } from "@vergeo/ui/src/status-chip";
import { useTranslations } from "next-intl";

type ListingProductStatusProps = {
  listingStatus: string;
  productStatus: string | null | undefined;
  /** Shown when a canonical product was rejected (WhatsApp / outbox copy). */
  rejectionReason?: string | null;
  className?: string;
};

/**
 * Buyer-visible truth: a listing can be Live while its canonical product is still
 * in moderation, so shoppers do not see it on Vergeo5 yet.
 */
export function ListingProductStatusChip({
  listingStatus,
  productStatus,
  rejectionReason,
  className,
}: ListingProductStatusProps) {
  const t = useTranslations("vendor");
  if (listingStatus !== "active") {
    return null;
  }
  if (productStatus === "pending_moderation") {
    return (
      <StatusChip
        tone="warning"
        label={t("listings.manage.productStatus.inReview")}
        className={className}
      />
    );
  }
  if (productStatus === "rejected" || rejectionReason) {
    return (
      <div className={`flex flex-col gap-1 ${className ?? ""}`.trim()}>
        <StatusChip tone="danger" label={t("listings.manage.productStatus.rejected")} />
        {rejectionReason ? (
          <p className="text-xs text-danger" role="note">
            {rejectionReason}
          </p>
        ) : null}
      </div>
    );
  }
  return null;
}
