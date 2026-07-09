"use client";

import { useTranslations } from "next-intl";

import type { SlaBadge } from "./api";

type SlaBadgeProps = {
  badge: SlaBadge;
};

const BADGE_STYLES: Record<SlaBadge, string> = {
  on_track: "border-[#2D6A4F] bg-[#E8F5EE] text-[#1B4332]",
  due_soon: "border-[#B7791F] bg-[#FFF8E6] text-[#744210]",
  overdue: "border-[#9B2C2C] bg-[#FDECEC] text-[#742A2A]",
};

export function SlaBadge({ badge }: SlaBadgeProps) {
  const t = useTranslations("admin.kyc.queue.sla");
  return (
    <span
      className={`inline-flex min-h-8 items-center rounded-full border px-2.5 text-xs font-medium ${BADGE_STYLES[badge]}`}
    >
      {t(badge)}
    </span>
  );
}
