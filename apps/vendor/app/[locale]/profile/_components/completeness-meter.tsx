"use client";

import { useTranslations } from "next-intl";

import type { CompletenessBreakdown } from "../_lib/profile-client";

type CompletenessMeterProps = {
  score: number;
  breakdown: CompletenessBreakdown;
};

const FIELD_KEYS = ["logo", "description", "hours", "location", "badge"] as const;

export function CompletenessMeter({ score, breakdown }: CompletenessMeterProps) {
  const t = useTranslations("vendor");

  return (
    <section
      aria-labelledby="profile-completeness-heading"
      className="rounded-xl border border-neutral-200 bg-neutral-50 p-4"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="profile-completeness-heading" className="text-sm font-semibold text-neutral-900">
          {t("profile.completeness.heading")}
        </h2>
        <span className="text-sm font-medium text-emerald-700">
          {t("profile.completeness.score", { score })}
        </span>
      </div>
      <div
        className="mb-3 h-2 overflow-hidden rounded-full bg-neutral-200"
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("profile.completeness.heading")}
      >
        <div
          className="h-full rounded-full bg-emerald-600 transition-[width] duration-300"
          style={{ width: `${score}%` }}
        />
      </div>
      <ul className="grid gap-2">
        {FIELD_KEYS.map((field) => (
          <li key={field} className="flex items-center gap-2 text-sm text-neutral-700">
            <span
              aria-hidden
              className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                breakdown[field]
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-neutral-200 text-neutral-500"
              }`}
            >
              {breakdown[field] ? "✓" : "·"}
            </span>
            <span>{t(`profile.completeness.fields.${field}`)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
