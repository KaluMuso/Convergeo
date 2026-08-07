import { loadNamespace, LOCALES, formatK, type Locale } from "@vergeo/i18n";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { getAccountAccessToken } from "../_components/account-server";

import type { RfqThread } from "../../../../lib/rfq-api";
import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string }>;
};

async function fetchListingQuotes(accessToken: string): Promise<RfqThread[]> {
  const base = getApiBaseUrl();
  if (!base) {
    return [];
  }
  const response = await fetch(`${base}/rfq?party=customer&limit=50`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) {
    return [];
  }
  const body = (await response.json()) as { items: RfqThread[] };
  return (body.items ?? []).filter((thread) => thread.listing_id !== null);
}

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountListingQuotesPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const messages = { ...baseMessages, account: accountMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account.listingQuotes" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const threads = await fetchListingQuotes(accessToken);

  if (threads.length === 0) {
    return (
      <section className="space-y-4 rounded border border-border bg-surface p-6 text-center">
        <h2 className="font-display text-h2 text-display-ink">{t("list.emptyTitle")}</h2>
        <p className="text-sm text-text-2">{t("list.emptyBody")}</p>
        <LinkButton
          href={`/${locale}/search`}
          variant="primary"
          className="px-5 text-sm"
          LinkComponent={Link}
        >
          {t("list.browseCta")}
        </LinkButton>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{t("list.title")}</h2>
        <p className="text-sm text-text-2">{t("list.intro")}</p>
      </header>

      <ul className="space-y-3">
        {threads.map((thread) => (
          <li key={thread.id}>
            <article className="flex flex-col gap-3 rounded border border-border bg-surface p-4">
              <div className="space-y-1">
                <p className="text-sm font-medium text-display-ink line-clamp-2">
                  {thread.requested_details}
                </p>
                <p className="text-xs text-text-2">
                  {t("list.posted", {
                    date: new Date(thread.created_at).toLocaleDateString(locale),
                  })}
                  {" · "}
                  {t("list.status", { status: t(`status.${thread.status}`) })}
                </p>
                {thread.quote_price_ngwee !== null ? (
                  <p className="text-sm font-mono text-text">
                    {t("list.quotedPrice", { amount: formatK(thread.quote_price_ngwee) })}
                  </p>
                ) : null}
              </div>
              <LinkButton
                href={`/${locale}/account/quotes/${thread.id}`}
                variant="secondary"
                className="shrink-0 self-end border-primary px-4 text-sm text-primary"
                LinkComponent={Link}
              >
                {t("list.viewCta")}
              </LinkButton>
            </article>
          </li>
        ))}
      </ul>
    </section>
  );
}
