"use client";

import { useTranslations } from "next-intl";

import { buildKycChecklist, type KycChecklistItemState } from "../_lib/kyc-checklist";

import type { KycApplication } from "../_lib/types";

const STATE_CLASSES: Record<KycChecklistItemState, string> = {
  not_started: "border-border bg-bg-2 text-text-2",
  saved: "border-border bg-bg-2 text-text-2",
  submitted: "border-info bg-info/10 text-info",
  under_review: "border-info bg-info/10 text-info",
  approved: "border-success bg-success/10 text-success",
  rejected: "border-danger bg-danger/10 text-danger",
};

const STATE_ICON: Record<KycChecklistItemState, string> = {
  not_started: "○",
  saved: "◐",
  submitted: "◐",
  under_review: "◔",
  approved: "✓",
  rejected: "!",
};

type KycChecklistCardProps = {
  application: KycApplication;
  locale: string;
  /** Hide the built-in CTA when the host screen already shows one. */
  showCta?: boolean;
};

/**
 * What verification needs, why each item is asked for, and where it stands —
 * with the reviewer's reason and a concrete fix when something was rejected.
 */
export function KycChecklistCard({ application, locale, showCta = true }: KycChecklistCardProps) {
  const t = useTranslations("vendor");
  const checklist = buildKycChecklist(application);
  const total = checklist.items.length;

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4"
      aria-labelledby="vendor-kyc-checklist-heading"
      data-testid="vendor-kyc-checklist"
      data-overall={checklist.overall}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="vendor-kyc-checklist-heading" className="text-base font-semibold text-text">
          {t("onboarding.checklist.heading")}
        </h2>
        <p className="shrink-0 text-xs font-medium text-text-2">
          {t("onboarding.checklist.progress", { done: checklist.doneCount, total })}
        </p>
      </div>

      <ol className="flex flex-col gap-2">
        {checklist.items.map((item) => {
          const isNext = checklist.nextKey === item.key;
          return (
            <li
              key={item.key}
              className={`flex gap-3 rounded-lg border p-3 ${
                isNext ? "border-primary bg-primary-tint" : "border-border"
              }`}
              data-item={item.key}
              data-state={item.state}
              aria-current={isNext ? "step" : undefined}
            >
              <span
                aria-hidden="true"
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${STATE_CLASSES[item.state]}`}
              >
                {STATE_ICON[item.state]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <p className="text-sm font-semibold text-text">
                    {t(`onboarding.checklist.items.${item.key}.title`)}
                  </p>
                  <span
                    className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATE_CLASSES[item.state]}`}
                  >
                    {t(`onboarding.checklist.states.${item.state}`)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-text-2">
                  {t(`onboarding.checklist.items.${item.key}.why`)}
                </p>
                {item.state === "rejected" && (item.key === "nrc" || item.key === "selfie") ? (
                  <p className="mt-1 text-sm font-medium text-text">
                    {t(`onboarding.checklist.fix.${item.key}`)}
                  </p>
                ) : null}
                {item.key === "review" && item.state === "rejected" ? (
                  <>
                    {application.rejection_reason ? (
                      <div className="mt-2 rounded-md bg-bg-2 p-2 text-sm">
                        <p className="font-medium text-text">
                          {t("onboarding.checklist.reasonLabel")}
                        </p>
                        <p className="text-text-2">{application.rejection_reason}</p>
                      </div>
                    ) : null}
                    <p className="mt-1 text-sm font-medium text-text">
                      {t("onboarding.checklist.fix.review")}
                    </p>
                  </>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {showCta && (checklist.overall === "draft" || checklist.overall === "needs_fix") ? (
        <a
          href={`/${locale}/onboarding`}
          className="inline-flex min-h-11 w-full items-center justify-center rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
          data-testid="vendor-kyc-checklist-cta"
        >
          {checklist.overall === "draft"
            ? t("onboarding.checklist.ctaFinish")
            : t("onboarding.checklist.ctaFix")}
        </a>
      ) : null}
      {checklist.overall === "pending" ? (
        <p className="text-sm text-text-2">{t("onboarding.checklist.pendingNote")}</p>
      ) : null}
    </section>
  );
}
