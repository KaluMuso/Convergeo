import { formatK, loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getAccountAccessToken } from "../_components/account-server";

import type { Metadata } from "next";

type JobSummary = {
  id: string;
  category: string;
  description: string;
  status: string;
  created_at: string;
  budget_band_min_ngwee: number | null;
  budget_band_max_ngwee: number | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function fetchCustomerJobs(accessToken: string): Promise<JobSummary[]> {
  const response = await fetch(`${getApiBaseUrl()}/jobs`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) {
    return [];
  }
  const body = (await response.json()) as { items: JobSummary[] };
  return body.items ?? [];
}

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountJobsPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const baseMessages = await getMessages();
  const servicesMessages = await loadNamespace(locale as Locale, "services");
  const messages = { ...baseMessages, services: servicesMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "services" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const jobs = await fetchCustomerJobs(accessToken);

  if (jobs.length === 0) {
    return (
      <section className="space-y-4 rounded border border-border bg-surface p-6 text-center">
        <h2 className="font-display text-h2 text-display-ink">{t("quotes.list.emptyTitle")}</h2>
        <p className="text-sm text-text-2">{t("quotes.list.emptyBody")}</p>
        <Link
          href={`/${locale}/services/post-job`}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-5 text-sm font-medium text-surface"
        >
          {t("quotes.list.postJobCta")}
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("quotes.list.title")}</h2>
        <p className="text-sm text-text-2">{t("quotes.list.intro")}</p>
      </header>

      <ul className="space-y-3">
        {jobs.map((job) => (
          <li key={job.id}>
            <article className="flex flex-col gap-3 rounded border border-border bg-surface p-4">
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-text-2">
                  {t(`postJob.category.${job.category}`, { default: job.category })}
                </p>
                <p className="text-sm font-medium text-display-ink">{job.description}</p>
                <p className="text-xs text-text-2">
                  {t("quotes.list.posted", {
                    date: new Date(job.created_at).toLocaleDateString(locale),
                  })}
                  {" · "}
                  {t("quotes.list.status", { status: t(`quotes.status.${job.status}`) })}
                </p>
              </div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-text-2">
                  {job.budget_band_min_ngwee != null || job.budget_band_max_ngwee != null
                    ? t("quotes.list.budget", {
                        min:
                          job.budget_band_min_ngwee != null
                            ? formatK(job.budget_band_min_ngwee)
                            : "—",
                        max:
                          job.budget_band_max_ngwee != null
                            ? formatK(job.budget_band_max_ngwee)
                            : "—",
                      })
                    : t("quotes.list.budgetFlexible")}
                </p>
                <Link
                  href={`/${locale}/account/jobs/${job.id}`}
                  className="inline-flex min-h-11 shrink-0 items-center rounded border border-primary px-4 text-sm font-medium text-primary"
                >
                  {t("quotes.list.compareCta")}
                </Link>
              </div>
            </article>
          </li>
        ))}
      </ul>
    </section>
  );
}
