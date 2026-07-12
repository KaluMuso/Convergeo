"use client";

import { useTranslations } from "next-intl";

import type { SlaBadge } from "./api";

type DisputeSlaBadgeProps = {
  badge: SlaBadge;
};

const BADGE_STYLES: Record<SlaBadge, string> = {
  on_track: "border-success bg-success/10 text-success",
  due_soon: "border-warning bg-warning/10 text-warning",
  overdue: "border-danger bg-danger/10 text-danger",
};

export function DisputeSlaBadge({ badge }: DisputeSlaBadgeProps) {
  const t = useTranslations("admin.disputes.queue.sla");
  return (
    <span
      className={`inline-flex min-h-8 items-center rounded-full border px-2.5 text-xs font-medium ${BADGE_STYLES[badge]}`}
    >
      {t(badge)}
    </span>
  );
}
