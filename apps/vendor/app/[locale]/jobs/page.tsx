"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../lib/api-base-url";
import { Badge, Button, FormField, Input, Spinner } from "../listings/new/_lib/ui";

type QuoteItem = {
  id: string;
  job_id: string;
  provider_vendor_id: string;
  amount_ngwee: number;
  message: string | null;
  status: string;
  expires_at: string | null;
  created_at: string;
};

type MatchedJob = {
  id: string;
  category: string;
  description: string;
  preferred_date: string | null;
  budget_band_min_ngwee: number | null;
  budget_band_max_ngwee: number | null;
  status: string;
  created_at: string;
  own_quote: QuoteItem | null;
};

function createJobsClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    listMatchedJobs(): Promise<{ items: MatchedJob[] }> {
      return client.request<{ items: MatchedJob[] }>("/provider/jobs");
    },
    submitQuote(
      jobId: string,
      payload: { amount_ngwee: number; message?: string; validity_days: number },
    ): Promise<{ quote: QuoteItem }> {
      return client.request<{ quote: QuoteItem }>(`/jobs/${jobId}/quotes`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    withdrawQuote(quoteId: string): Promise<{ quote: QuoteItem }> {
      return client.request<{ quote: QuoteItem }>(`/quotes/${quoteId}/withdraw`, {
        method: "POST",
      });
    },
  };
}

function zmwDecimalToNgwee(input: string): number {
  const cleaned = input.replace(/,/g, "").trim();
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) {
    throw new Error("invalid_zmw_decimal");
  }
  const major = BigInt(match[1] ?? "0");
  const minorPart = match[2] ?? "00";
  const minor = BigInt(minorPart.padEnd(2, "0"));
  return Number(major * 100n + minor);
}

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default function VendorJobsPage({ params }: PageProps) {
  const [locale, setLocale] = useState("en");
  const t = useTranslations("vendor.jobs");
  const { session, loading: sessionLoading } = useSession();
  const [jobs, setJobs] = useState<MatchedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const [validityDays, setValidityDays] = useState("7");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    void params.then(({ locale: nextLocale }) => setLocale(nextLocale));
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const jobsClient = useMemo(() => createJobsClient(getToken), [getToken]);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await jobsClient.listMatchedJobs();
      setJobs(response.items);
      setError(null);
    } catch {
      setError(t("errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [jobsClient, t]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadJobs();
  }, [loadJobs, session, sessionLoading]);

  const handleSubmitQuote = async (jobId: string) => {
    setFormError(null);
    let amountNgwee: number;
    try {
      amountNgwee = zmwDecimalToNgwee(amount);
      if (amountNgwee <= 0) {
        setFormError(t("quoteForm.amountInvalid"));
        return;
      }
    } catch {
      setFormError(t("quoteForm.amountInvalid"));
      return;
    }

    const days = Number.parseInt(validityDays, 10);
    if (!Number.isFinite(days) || days < 1 || days > 30) {
      setFormError(t("quoteForm.validityInvalid"));
      return;
    }

    setSubmitting(true);
    try {
      await jobsClient.submitQuote(jobId, {
        amount_ngwee: amountNgwee,
        message: message.trim() || undefined,
        validity_days: days,
      });
      setAmount("");
      setMessage("");
      setActiveJobId(null);
      await loadJobs();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setFormError(t("errors.notMatched"));
      } else if (err instanceof ApiError && err.status === 409) {
        setFormError(t("errors.alreadyQuoted"));
      } else {
        setFormError(t("errors.submitFailed"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleWithdraw = async (quoteId: string) => {
    setSubmitting(true);
    try {
      await jobsClient.withdrawQuote(quoteId);
      await loadJobs();
    } catch {
      setError(t("errors.withdrawFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionLoading || loading) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
        <div className="flex min-h-[40vh] items-center justify-center">
          <Spinner label={t("loading")} />
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col p-4">
        <p className="text-sm text-text-2">{t("authRequired")}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col gap-4 p-4">
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-text-2">{t("eyebrow")}</p>
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {jobs.length === 0 ? (
        <section className="rounded border border-border bg-surface p-6 text-center">
          <p className="text-sm text-text-2">{t("empty")}</p>
        </section>
      ) : (
        <ul className="space-y-4">
          {jobs.map((job) => (
            <li key={job.id} className="space-y-3 rounded border border-border bg-surface p-4">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant="new"
                    label={t(`categories.${job.category}`, { default: job.category })}
                  />
                  {job.own_quote ? (
                    <Badge variant="free" label={t("status.quoted")} />
                  ) : (
                    <Badge variant="public" label={t("status.new")} />
                  )}
                </div>
                <p className="text-sm font-medium text-display-ink">{job.description}</p>
                <p className="text-xs text-text-2">
                  {t("posted", { date: new Date(job.created_at).toLocaleDateString(locale) })}
                </p>
              </div>

              {job.own_quote && job.own_quote.status === "submitted" ? (
                <div className="space-y-2 rounded bg-bg-2 p-3">
                  <p className="font-mono text-sm text-display-ink">
                    {t("yourQuote", { amount: formatK(job.own_quote.amount_ngwee) })}
                  </p>
                  {job.own_quote.message ? (
                    <p className="text-xs text-text-2">{job.own_quote.message}</p>
                  ) : null}
                  <Button
                    type="button"
                    variant="secondary"
                    loading={submitting}
                    loadingLabel={t("quoteForm.withdrawing")}
                    disabled={submitting}
                    onClick={() => void handleWithdraw(job.own_quote!.id)}
                  >
                    {t("quoteForm.withdraw")}
                  </Button>
                </div>
              ) : activeJobId === job.id ? (
                <div className="space-y-3 border-t border-border pt-3">
                  <FormField id={`amount-${job.id}`} label={t("quoteForm.amountLabel")}>
                    <Input
                      inputMode="decimal"
                      placeholder={t("quoteForm.amountPlaceholder")}
                      value={amount}
                      onChange={(event) => setAmount(event.target.value)}
                    />
                  </FormField>
                  <FormField id={`message-${job.id}`} label={t("quoteForm.messageLabel")}>
                    <Input
                      value={message}
                      onChange={(event) => setMessage(event.target.value)}
                      placeholder={t("quoteForm.messagePlaceholder")}
                    />
                  </FormField>
                  <FormField id={`validity-${job.id}`} label={t("quoteForm.validityLabel")}>
                    <Input
                      inputMode="numeric"
                      value={validityDays}
                      onChange={(event) => setValidityDays(event.target.value)}
                    />
                  </FormField>
                  {formError ? <p className="text-sm text-danger">{formError}</p> : null}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      loading={submitting}
                      loadingLabel={t("quoteForm.submitting")}
                      disabled={submitting}
                      onClick={() => void handleSubmitQuote(job.id)}
                    >
                      {t("quoteForm.submit")}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      loadingLabel={t("quoteForm.cancel")}
                      disabled={submitting}
                      onClick={() => {
                        setActiveJobId(null);
                        setFormError(null);
                      }}
                    >
                      {t("quoteForm.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  loadingLabel={t("quoteForm.open")}
                  onClick={() => setActiveJobId(job.id)}
                >
                  {t("quoteForm.open")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
