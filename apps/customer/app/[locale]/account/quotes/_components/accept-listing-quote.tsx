"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { refreshCart } from "../../../(shop)/_components/cart/mini-cart-drawer";
import { createRfqApiClient } from "../../../../../lib/rfq-api";

import type { RfqThread } from "../../../../../lib/rfq-api";

type AcceptListingQuoteProps = {
  locale: string;
  thread: RfqThread;
};

export function AcceptListingQuote({ locale, thread }: AcceptListingQuoteProps) {
  const t = useTranslations("account.listingQuotes.accept");
  const { session } = useSession();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const quotePrice = thread.quote_price_ngwee ?? 0;

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const rfqClient = useMemo(() => createRfqApiClient(getToken), [getToken]);

  const handleAccept = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      await rfqClient.acceptQuoteIntoCart(thread.id, 1);
      await refreshCart();
      setSuccess(true);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === "rfq.quote_expired") {
        setError(t("errors.expired"));
      } else if (err instanceof ApiError && err.code === "rfq.not_quoted") {
        setError(t("errors.invalidStatus"));
      } else if (err instanceof ApiError && err.status === 401) {
        setError(t("errors.signInRequired"));
      } else if (err instanceof ApiError && err.status === 429) {
        setError(t("errors.rateLimited"));
      } else {
        setError(t("errors.generic"));
      }
      setSubmitting(false);
    }
  }, [rfqClient, router, t, thread.id]);

  if (success) {
    return (
      <section
        className="space-y-3 rounded border border-border bg-surface p-4"
        data-testid="listing-quote-accept-success"
      >
        <p className="font-medium text-text">{t("successTitle")}</p>
        <p className="text-sm text-text-2">{t("successBody")}</p>
        <Link
          href={`/${locale}/cart`}
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-2 hover:underline"
          data-testid="listing-quote-view-cart"
        >
          {t("viewCart")}
        </Link>
      </section>
    );
  }

  return (
    <section className="space-y-4 rounded border border-border bg-surface p-4">
      <header className="space-y-1">
        <h3 className="font-display text-h3 text-display-ink">{t("title")}</h3>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      <dl className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-text-2">{t("quotedPriceLabel")}</dt>
          <dd className="font-mono text-lg font-semibold text-display-ink">
            {formatK(quotePrice)}
          </dd>
        </div>
      </dl>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <Button
        type="button"
        variant="primary"
        loading={submitting}
        loadingLabel={t("submitting")}
        disabled={submitting}
        data-testid="listing-quote-accept-cta"
        onClick={() => void handleAccept()}
      >
        {t("confirmCta")}
      </Button>
    </section>
  );
}
