import { LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { setRequestLocale } from "next-intl/server";

import { getAccountAccessToken, getAccountTranslator } from "../_components/account-server";

import { createBusinessApiClient, type BusinessStatus } from "./_components/business-api";
import { BusinessApplyForm } from "./_components/business-apply-form";

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

const EMPTY_STATUS: BusinessStatus = {
  has_application: false,
  status: null,
  eligible: false,
  legal_name: null,
  registration_no: null,
  tpin: null,
  reviewer_notes: null,
};

export default async function AccountBusinessPage({ params }: PageProps) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }
  setRequestLocale(locale);

  const accessToken = await getAccountAccessToken(locale);
  const t = await getAccountTranslator(locale);

  const api = createBusinessApiClient(() => accessToken);
  let status: BusinessStatus;
  try {
    status = await api.getStatus();
  } catch {
    status = EMPTY_STATUS;
  }

  const statusKey = status.status ?? "none";
  const showForm = statusKey === "none" || statusKey === "rejected";

  const formLabels = {
    legalNameLabel: t("business.legalNameLabel"),
    legalNamePlaceholder: t("business.legalNamePlaceholder"),
    registrationLabel: t("business.registrationLabel"),
    registrationPlaceholder: t("business.registrationPlaceholder"),
    tpinLabel: t("business.tpinLabel"),
    tpinPlaceholder: t("business.tpinPlaceholder"),
    submit: t("business.submit"),
    submitting: t("business.submitting"),
    resubmit: t("business.resubmit"),
    submitted: t("business.submitted"),
    errorRequired: t("business.errors.required"),
    errorFailed: t("business.errors.failed"),
    errorRateLimited: t("business.errors.rateLimited"),
    errorAlreadyDecided: t("business.errors.alreadyDecided"),
  };

  return (
    <section className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="font-display text-h2 text-display-ink">{t("business.title")}</h2>
        <p className="text-sm text-text-2">{t("business.description")}</p>
      </header>

      <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-2 px-3 py-2 text-sm">
        <span className="text-text-2">{t("business.statusLabel")}</span>
        <span className="font-semibold text-text">{t(`business.status.${statusKey}`)}</span>
      </div>

      {statusKey === "verified" ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
          <p className="font-semibold text-text">{t("business.verifiedTitle")}</p>
          <p className="text-sm text-text-2">{t("business.verifiedBody")}</p>
          <Link
            href={`/${locale}/supplies`}
            className="inline-flex min-h-11 w-fit items-center rounded-md bg-primary px-4 text-sm font-medium text-surface"
          >
            {t("business.browseSupplies")}
          </Link>
        </div>
      ) : null}

      {statusKey === "pending" || statusKey === "suspended" ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
          <p className="font-semibold text-text">{t("business.pendingTitle")}</p>
          <p className="text-sm text-text-2">{t("business.pendingBody")}</p>
        </div>
      ) : null}

      {statusKey === "rejected" && status.reviewer_notes ? (
        <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-4">
          <p className="text-sm font-semibold text-text">{t("business.reviewerNotesLabel")}</p>
          <p className="text-sm text-text-2">{status.reviewer_notes}</p>
        </div>
      ) : null}

      {showForm ? (
        <BusinessApplyForm
          locale={locale}
          initial={status}
          labels={formLabels}
          accessToken={accessToken}
        />
      ) : null}
    </section>
  );
}
