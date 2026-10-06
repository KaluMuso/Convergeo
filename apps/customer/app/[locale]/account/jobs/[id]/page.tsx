"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Badge } from "@vergeo/ui/src/badge";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Spinner } from "@vergeo/ui/src/spinner";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { useSession } from "../../../../../lib/customer-session";

import { AcceptFlow } from "./_components/accept-flow";
import { CompleteConfirm } from "./_components/complete-confirm";
import { canAcceptQuote, shouldShowCompletion } from "./_components/job-status";
import { ServiceReviewForm } from "./_components/service-review-form";

type JobDetail = {
  id: string;
  status: string;
};

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

function createQuotesClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    getJob(jobId: string): Promise<JobDetail> {
      return client.request<JobDetail>(`/jobs/${jobId}`);
    },
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
  const { locale, id: jobId } = use(params);
  const t = useTranslations("services.quotes");
  const { session, loading: sessionLoading, generation } = useSession();

  if (sessionLoading) {
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
    <JobCompareContent
      key={`${generation}:${session.user.id}:${jobId}`}
      locale={locale}
      jobId={jobId}
      accessToken={session.access_token}
    />
  );
}

function JobCompareContent({
  locale,
  jobId,
  accessToken,
}: {
  locale: string;
  jobId: string;
  accessToken: string;
}) {
  const t = useTranslations("services.quotes");
  const tb = useTranslations("services.badges");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [quotes, setQuotes] = useState<QuoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [declineQuoteId, setDeclineQuoteId] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const requestId = useRef(0);
  const mounted = useRef(true);
  const hasLoaded = useRef(false);
  const pendingAccepts = useRef(new Set<string>());

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, []);

  const getToken = useCallback(() => accessToken, [accessToken]);
  const quotesClient = useMemo(() => createQuotesClient(getToken), [getToken]);

  const loadJobAndQuotes = useCallback(async () => {
    if (!mounted.current || pendingAccepts.current.size > 0) return;
    const currentRequest = ++requestId.current;
    if (!hasLoaded.current) setLoading(true);
    try {
      const [jobResponse, response] = await Promise.all([
        quotesClient.getJob(jobId),
        quotesClient.listQuotes(jobId),
      ]);
      if (!mounted.current || currentRequest !== requestId.current) return;
      // Keep any accepting quote mounted until its POST settles.
      if (pendingAccepts.current.size > 0) return;
      setJob(jobResponse);
      setQuotes(response.items);
      setError(null);
      hasLoaded.current = true;
    } catch (err) {
      if (!mounted.current || currentRequest !== requestId.current) return;
      const accessDenied = err instanceof ApiError && (err.status === 401 || err.status === 403);
      // A transient refresh failure must not discard an accepting flow. A
      // permission failure still clears private data immediately.
      if (pendingAccepts.current.size > 0 && !accessDenied) return;
      pendingAccepts.current.clear();
      setJob(null);
      setQuotes([]);
      setDeclineQuoteId(null);
      setDeclineReason("");
      setSubmitting(false);
      if (err instanceof ApiError && err.status === 403) {
        setError(t("errors.forbidden"));
      } else {
        setError(t("errors.loadFailed"));
      }
    } finally {
      if (mounted.current && currentRequest === requestId.current) {
        setLoading(false);
      }
    }
  }, [jobId, quotesClient, t]);
  const latestLoad = useRef(loadJobAndQuotes);
  latestLoad.current = loadJobAndQuotes;

  const handleAcceptPendingChange = (quoteId: string, pending: boolean) => {
    if (pending) {
      pendingAccepts.current.add(quoteId);
    } else {
      pendingAccepts.current.delete(quoteId);
      if (pendingAccepts.current.size === 0) void latestLoad.current();
    }
  };

  useEffect(() => {
    void loadJobAndQuotes();
  }, [loadJobAndQuotes]);

  const handleDecline = async (quoteId: string) => {
    setSubmitting(true);
    try {
      await quotesClient.declineQuote(quoteId, declineReason.trim() || undefined);
      if (!mounted.current) return;
      setDeclineQuoteId(null);
      setDeclineReason("");
      await latestLoad.current();
    } catch {
      if (mounted.current) {
        setError(t("errors.declineFailed"));
      }
    } finally {
      if (mounted.current) {
        setSubmitting(false);
      }
    }
  };

  const acceptedQuote = quotes.find((quote) => quote.status === "accepted") ?? null;

  if (loading) {
    return (
      <section className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <Link href={`/${locale}/account/jobs`} className="text-sm font-medium text-primary">
          {t("back")}
        </Link>
        <h2 className="font-display text-h2 text-display-ink">{t("compareTitle")}</h2>
        <p className="text-sm text-text-2">{t("compareIntro")}</p>
        {job ? (
          <p className="text-xs text-text-2">
            {t("list.status", { status: t(`status.${job.status}`) })}
          </p>
        ) : null}
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

              {canAcceptQuote(job?.status, quote.status) ? (
                <AcceptFlow
                  locale={locale}
                  jobId={jobId}
                  quoteId={quote.id}
                  vendorName={quote.provider?.display_name ?? t("unknownProvider")}
                  totalNgwee={quote.amount_ngwee}
                  onPendingChange={(pending) => handleAcceptPendingChange(quote.id, pending)}
                />
              ) : null}

              {declineQuoteId === quote.id && canAcceptQuote(job?.status, quote.status) ? (
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
              ) : canAcceptQuote(job?.status, quote.status) ? (
                <Button
                  type="button"
                  variant="secondary"
                  className="mt-auto"
                  loadingLabel={t("decline.open")}
                  onClick={() => setDeclineQuoteId(quote.id)}
                >
                  {t("decline.open")}
                </Button>
              ) : quote.status === "accepted" ? (
                <Badge variant="public" label={t("status.accepted")} />
              ) : null}
            </article>
          ))}
        </div>
      )}

      {shouldShowCompletion(job?.status, acceptedQuote?.status) && acceptedQuote ? (
        <CompleteConfirm
          jobId={jobId}
          allowConfirmAttempt
          onConfirmed={() => void loadJobAndQuotes()}
        />
      ) : null}

      {job ? <ServiceReviewForm jobId={jobId} /> : null}
    </section>
  );
}
