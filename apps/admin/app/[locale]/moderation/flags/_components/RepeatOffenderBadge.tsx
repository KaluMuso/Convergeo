"use client";

import { useTranslations } from "next-intl";

type RepeatOffenderBadgeProps = {
  count: number;
};

export function RepeatOffenderBadge({ count }: RepeatOffenderBadgeProps) {
  const t = useTranslations("admin.flags.queue");

  if (count < 2) {
    return null;
  }

  return (
    <span className="inline-flex items-center rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
      {t("repeatOffender", { count })}
    </span>
  );
}
