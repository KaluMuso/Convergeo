"use client";

import { useTranslations } from "next-intl";

const MEANWHILE_KEYS = ["cod", "prepaid", "questions"] as const;
const LATER_KEYS = ["held", "released", "history", "statement"] as const;

/**
 * Pilot state for Payouts: plainly says payouts are not switched on, how money
 * is handled meanwhile, and what this screen will show later. No balances and
 * no buttons — nothing here pretends money can move.
 */
export function PayoutsPilotNotice() {
  const t = useTranslations("vendor");

  return (
    <div className="flex flex-col gap-5" data-testid="vendor-payouts-pilot">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-text-2">{t("payouts.eyebrow")}</p>
        <h1 className="font-display text-2xl font-semibold">{t("payouts.title")}</h1>
      </header>

      <section
        className="flex flex-col gap-2 rounded-xl border border-info/40 bg-info/10 p-4 text-text"
        role="status"
        aria-labelledby="vendor-payouts-pilot-title"
      >
        <span className="inline-flex self-start rounded-full border border-info bg-surface px-2.5 py-0.5 text-xs font-medium text-info">
          {t("payouts.pilot.badge")}
        </span>
        <h2 id="vendor-payouts-pilot-title" className="text-base font-semibold">
          {t("payouts.pilot.title")}
        </h2>
        <p className="text-sm">{t("payouts.pilot.body")}</p>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-text">{t("payouts.pilot.meanwhileHeading")}</h2>
        <ul className="flex flex-col gap-2">
          {MEANWHILE_KEYS.map((key) => (
            <li key={key} className="flex gap-2 text-sm text-text-2">
              <span
                aria-hidden="true"
                className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
              />
              <span>{t(`payouts.pilot.meanwhile.${key}`)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-dashed border-border p-4">
        <h2 className="text-sm font-semibold text-text">{t("payouts.pilot.laterHeading")}</h2>
        <ul className="flex flex-col gap-2">
          {LATER_KEYS.map((key) => (
            <li key={key} className="flex gap-2 text-sm text-text-2">
              <span
                aria-hidden="true"
                className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-text-3"
              />
              <span>{t(`payouts.pilot.later.${key}`)}</span>
            </li>
          ))}
        </ul>
        <p className="text-sm text-text">{t("payouts.pilot.notify")}</p>
      </section>
    </div>
  );
}
