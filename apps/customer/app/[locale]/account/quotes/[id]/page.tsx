import { loadNamespace, LOCALES, formatK, type Locale } from "@vergeo/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { getAccountAccessToken } from "../../_components/account-server";
import { AcceptListingQuote } from "../_components/accept-listing-quote";
import {
  canAcceptListingQuote,
  listingQuoteDisplayStatus,
} from "../_components/listing-quote-status";

import type { RfqThread } from "../../../../../lib/rfq-api";
import type { Metadata } from "next";

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

async function fetchThread(accessToken: string, threadId: string): Promise<RfqThread | null> {
  const base = getApiBaseUrl();
  if (!base) {
    return null;
  }
  const response = await fetch(`${base}/rfq/${encodeURIComponent(threadId)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as RfqThread;
}

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AccountListingQuoteDetailPage({ params }: PageProps) {
  const { locale, id } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const accessToken = await getAccountAccessToken(locale);
  const thread = await fetchThread(accessToken, id);

  if (thread === null || thread.listing_id === null) {
    notFound();
  }

  const baseMessages = await getMessages();
  const accountMessages = await loadNamespace(locale as Locale, "account");
  const messages = { ...baseMessages, account: accountMessages } as AbstractIntlMessages;
  const t = createTranslator({ locale, messages, namespace: "account.listingQuotes" }) as (
    key: string,
    values?: Record<string, string | number>,
  ) => string;

  const displayStatus = listingQuoteDisplayStatus(thread);
  const showAccept = canAcceptListingQuote(thread);

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link
          href={`/${locale}/account/quotes`}
          className="text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          {t("detail.back")}
        </Link>
        <h2 className="font-display text-h2 text-display-ink">{t("detail.title")}</h2>
        <p className="text-sm text-text-2">
          {t("detail.statusLabel")}: {t(`status.${displayStatus}`)}
        </p>
      </header>

      <article className="space-y-3 rounded border border-border bg-surface p-4">
        <h3 className="text-sm font-medium text-text-2">{t("detail.requestLabel")}</h3>
        <p className="text-sm text-text">{thread.requested_details}</p>
        {thread.quote_price_ngwee !== null ? (
          <p className="text-sm font-mono text-display-ink">
            {t("detail.quotedPrice", { amount: formatK(thread.quote_price_ngwee) })}
          </p>
        ) : null}
        {thread.quote_valid_until ? (
          <p className="text-xs text-text-2">
            {t("detail.validUntil", {
              date: new Date(thread.quote_valid_until).toLocaleDateString(locale),
            })}
          </p>
        ) : null}
      </article>

      {displayStatus === "pending" ? (
        <p className="text-sm text-text-2" data-testid="listing-quote-pending">
          {t("detail.pendingBody")}
        </p>
      ) : null}

      {displayStatus === "quoted_expired" ? (
        <p className="text-sm text-danger" data-testid="listing-quote-expired">
          {t("detail.expiredBody")}
        </p>
      ) : null}

      {displayStatus === "accepted" ? (
        <div className="space-y-2" data-testid="listing-quote-accepted">
          <p className="text-sm text-text-2">{t("detail.acceptedBody")}</p>
          <Link
            href={`/${locale}/cart`}
            className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
          >
            {t("detail.viewCart")}
          </Link>
        </div>
      ) : null}

      {displayStatus === "rejected" ? (
        <p className="text-sm text-text-2" data-testid="listing-quote-rejected">
          {t("detail.rejectedBody")}
        </p>
      ) : null}

      {showAccept ? <AcceptListingQuote locale={locale} thread={thread} /> : null}
    </section>
  );
}
