"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Spinner } from "@vergeo/ui/src/spinner";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

type QuoteProvider = {
  vendor_id: string;
  slug: string;
  display_name: string;
  preferred_badge: boolean;
  rating_avg: number | null;
  rating_count: number;
  response_time_tier: "fast" | "same_day" | "slow" | null;
};

type QuoteItem = {
  id: string;
  amount_ngwee: number;
  message: string | null;
  status: string;
  expires_at: string | null;
  created_at: string;
  provider: QuoteProvider | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function createQuotesClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    listQuotes(jobId: string): Promise<{ items: QuoteItem[]; view: string }> {
      return client.request<{ items: QuoteItem[]; view: string }>(`/jobs/${jobId}/quotes`);
    },
    declineQuote(quoteId: string, reason?: string): Promise<void> {
      return client.request(`/quotes/${quoteId}/decline`, {
        method: "POST",
        body: JSON.stringify({ reason: reason ?? null }),
      });
    },
  };
}

type PageProps = {
  params: Promise<{ locale: string; id: string }>;
};

export default function JobComparePage({ params }: PageProps) {
  const [locale, setLocale] = useState("en");
  const [jobId, setJobId] = useState("");
  const t = useTranslations("services.quotes");
  const tb = useTranslations("services.badges");
  const { session, loading: sessionLoading } = useSession();
  const [quotes, setQuotes] = useState<QuoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [declineQuoteId, setDeclineQuoteId] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void params.then(({ locale: nextLocale, id }) => {
      setLocale(nextLocale);
      setJobId(id);
    });
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const quotesClient = useMemo(() => createQuotesClient(getToken), [getToken]);

  const loadQuotes = useCallback(async () => {
    if (!jobId) {
      return;
    }
    setLoading(true);
    try {
      const response = await quotesClient.listQuotes(jobId);
      setQuotes(response.items);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(t("errors.forbidden"));
      } else {
        setError(t("errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [jobId, quotesClient, t]);

  useEffect(() => {
    if (sessionLoading || !jobId) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadQuotes();
  }, [jobId, loadQuotes, session, sessionLoading]);

  const handleDecline = async (quoteId: string) => {
    setSubmitting(true);
    try {
      await quotesClient.declineQuote(quoteId, declineReason.trim() || undefined);
      setDeclineQuoteId(null);
      setDeclineReason("");
      await loadQuotes();
    } catch {
      setError(t("errors.declineFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionLoading || loading) {
    return (
      <section className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </section>
    );
  }

  if (!session) {
    return <p className="text-sm text-text-2">{t("authRequired")}</p>;
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link href={`/${locale}/account/jobs`} className="text-sm font-medium text-primary">
          {t("back")}
        </Link>
        <h2 className="font-display text-h2 text-display-ink">{t("compareTitle")}</h2>
        <p className="text-sm text-text-2">{t("compareIntro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {quotes.length === 0 ? (
        <div className="rounded border border-border bg-surface p-6 text-center">
          <p className="text-sm text-text-2">{t("empty")}</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {quotes.map((quote) => (
            <article
              key={quote.id}
              className="flex flex-col gap-3 rounded border border-border bg-surface p-4"
            >
              <header className="space-y-1 border-b border-border pb-3">
                <p className="text-sm font-medium text-display-ink">
                  {quote.provider?.display_name ?? t("unknownProvider")}
                </p>
                <p className="font-mono text-lg text-display-ink">{formatK(quote.amount_ngwee)}</p>
              </header>

              <div className="flex flex-wrap gap-2">
                {quote.provider?.preferred_badge ? (
                  <Badge variant="free" label={t("preferredBadge")} />
                ) : null}
                {quote.provider?.response_time_tier ? (
                  <Badge variant="public" label={tb(quote.provider.response_time_tier)} />
                ) : null}
                {quote.provider?.rating_avg != null ? (
                  <Badge
                    variant="new"
                    label={t("rating", {
                      rating: quote.provider.rating_avg.toFixed(1),
                      count: quote.provider.rating_count,
                    })}
                  />
                ) : null}
              </div>

              {quote.message ? <p className="text-sm text-text-2">{quote.message}</p> : null}

              {quote.expires_at ? (
                <p className="text-xs text-text-2">
                  {t("validUntil", {
                    date: new Date(quote.expires_at).toLocaleDateString(locale),
                  })}
                </p>
              ) : null}

              {declineQuoteId === quote.id ? (
                <div className="mt-auto space-y-2 border-t border-border pt-3">
                  <FormField id={`decline-${quote.id}`} label={t("decline.reasonLabel")}>
                    <Input
                      value={declineReason}
                      onChange={(event) => setDeclineReason(event.target.value)}
                      placeholder={t("decline.reasonPlaceholder")}
                    />
                  </FormField>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      loading={submitting}
                      loadingLabel={t("decline.submitting")}
                      disabled={submitting}
                      onClick={() => void handleDecline(quote.id)}
                    >
                      {t("decline.submit")}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      loadingLabel={t("decline.cancel")}
                      disabled={submitting}
                      onClick={() => {
                        setDeclineQuoteId(null);
                        setDeclineReason("");
                      }}
                    >
                      {t("decline.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  className="mt-auto"
                  loadingLabel={t("decline.open")}
                  onClick={() => setDeclineQuoteId(quote.id)}
                >
                  {t("decline.open")}
                </Button>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
