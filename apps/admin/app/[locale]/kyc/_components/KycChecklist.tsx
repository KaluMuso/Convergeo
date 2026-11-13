"use client";

import { useTranslations } from "next-intl";

export const KYC_CHECKS = ["nrcLegible", "nameMatches", "selfieMatches", "notExpired"] as const;
export type KycCheckKey = (typeof KYC_CHECKS)[number];
export type KycChecks = Record<KycCheckKey, boolean>;

export const EMPTY_CHECKS: KycChecks = {
  nrcLegible: false,
  nameMatches: false,
  selfieMatches: false,
  notExpired: false,
};

export function isChecklistComplete(checks: KycChecks): boolean {
  return KYC_CHECKS.every((key) => checks[key]);
}

type Props = {
  checks: KycChecks;
  onChange: (next: KycChecks) => void;
  disabled?: boolean;
  /** MoMo name check result, shown as a hint beside the name item. */
  momoMatched: boolean | null;
};

/** Reviewer checklist. Local to the session; Approve stays disabled until all are ticked. */
export function KycChecklist({ checks, onChange, disabled = false, momoMatched }: Props) {
  const t = useTranslations("admin.kyc.checklist");
  const done = KYC_CHECKS.filter((key) => checks[key]).length;
  return (
    <fieldset
      className="space-y-1 rounded-lg border border-border bg-surface p-4"
      disabled={disabled}
      data-testid="kyc-checklist"
    >
      <legend className="px-1 text-sm font-semibold text-text">
        {t("title")}{" "}
        <span className="font-normal text-muted">
          {t("progress", { done, total: KYC_CHECKS.length })}
        </span>
      </legend>
      {KYC_CHECKS.map((key) => (
        <label key={key} className="flex min-h-11 items-start gap-3 py-1 text-sm">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4"
            checked={checks[key]}
            onChange={(event) => onChange({ ...checks, [key]: event.target.checked })}
          />
          <span className="text-text">
            {t(`items.${key}`)}
            {key === "nameMatches" && momoMatched !== null ? (
              <span className={`block text-xs ${momoMatched ? "text-success" : "text-danger"}`}>
                {momoMatched ? t("momoMatched") : t("momoMismatch")}
              </span>
            ) : null}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
