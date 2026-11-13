"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "../../../../../lib/customer-session";
import { createRfqApiClient, type RfqThread } from "../../../../../lib/rfq-api";

import { AcceptListingQuote } from "./accept-listing-quote";
import { canAcceptListingQuote, listingQuoteDisplayStatus } from "./listing-quote-status";

export function QuoteDetailClient({
  locale,
  threadId,
  refreshKey,
}: {
  locale: string;
  threadId: string;
  refreshKey: string;
}) {
  const { session, loading, generation } = useSession();

  if (loading || !session) return null;

  return (
    <CurrentAccountQuote
      key={`${generation}:${session.user.id}:${threadId}:${refreshKey}`}
      locale={locale}
      threadId={threadId}
      userId={session.user.id}
      accessToken={session.access_token}
    />
  );
}

function CurrentAccountQuote({
  locale,
  threadId,
  userId,
  accessToken,
}: {
  locale: string;
  threadId: string;
  userId: string;
  accessToken: string;
}) {
  const t = useTranslations("account.listingQuotes");
  const [thread, setThread] = useState<RfqThread | null>(null);
  const [loading, setLoading] = useState(true);
  const loadId = useRef(0);
  const client = useMemo(() => createRfqApiClient(() => accessToken), [accessToken]);

  useEffect(() => {
    const currentLoad = ++loadId.current;
    setThread(null);
    setLoading(true);
    void client.getThread(threadId).then(
      (response) => {
        if (loadId.current !== currentLoad) return;
        // The API owns authorization; check the returned identity too before rendering it.
        setThread(
          response.id === threadId &&
            response.customer_id === userId &&
            response.listing_id !== null
            ? response
            : null,
        );
        setLoading(false);
      },
      () => {
        if (loadId.current !== currentLoad) return;
        setThread(null);
        setLoading(false);
      },
    );
    return () => {
      loadId.current += 1;
    };
  }, [client, threadId, userId]);

  if (loading) return null;
  if (!thread) return <p className="text-sm text-text-2">{t("status.error")}</p>;

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
            {t("detail.quotedPrice", {
              amount: formatK(thread.quote_price_ngwee),
            })}
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
