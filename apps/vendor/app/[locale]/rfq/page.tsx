"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../lib/api-base-url";
import { Badge, Button, FormField, Input, Spinner } from "../listings/new/_lib/ui";

type RfqThread = {
  id: string;
  customer_id: string;
  vendor_id: string;
  listing_id: string | null;
  service_id: string | null;
  requested_details: string;
  status: string;
  quote_price_ngwee: number | null;
  quote_valid_until: string | null;
  quoted_at: string | null;
  last_message_at: string | null;
  created_at: string;
};

function createRfqVendorClient(getToken: () => string | null | Promise<string | null>) {
  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken });
  return {
    listThreads(): Promise<{ items: RfqThread[] }> {
      return client.request<{ items: RfqThread[] }>("/rfq?party=vendor&limit=50");
    },
    issueQuote(
      threadId: string,
      payload: { price_ngwee: number; validity_days: number; message?: string },
    ): Promise<RfqThread> {
      return client.request<RfqThread>(`/rfq/${threadId}/quote`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    reject(threadId: string): Promise<RfqThread> {
      return client.request<RfqThread>(`/rfq/${threadId}/reject`, { method: "POST" });
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

export default function VendorRfqPage({ params }: PageProps) {
  const [locale, setLocale] = useState("en");
  const t = useTranslations("vendor.rfq");
  const { session, loading: sessionLoading } = useSession();
  const [threads, setThreads] = useState<RfqThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const [validityDays, setValidityDays] = useState("7");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    void params.then(({ locale: nextLocale }) => setLocale(nextLocale));
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const rfqClient = useMemo(() => createRfqVendorClient(getToken), [getToken]);

  const loadThreads = useCallback(async () => {
    setLoading(true);
    try {
      const response = await rfqClient.listThreads();
      setThreads(response.items);
      setError(null);
    } catch {
      setError(t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [rfqClient, t]);

  useEffect(() => {
    if (!sessionLoading && session?.access_token) {
      void loadThreads();
    }
  }, [loadThreads, session?.access_token, sessionLoading]);

  const handleSubmitQuote = async (threadId: string) => {
    setFormError(null);
    let priceNgwee: number;
    try {
      priceNgwee = zmwDecimalToNgwee(amount);
    } catch {
      setFormError(t("quoteForm.invalidAmount"));
      return;
    }
    if (priceNgwee <= 0) {
      setFormError(t("quoteForm.invalidAmount"));
      return;
    }
    const days = Number.parseInt(validityDays, 10);
    if (!Number.isFinite(days) || days < 1) {
      setFormError(t("quoteForm.invalidValidity"));
      return;
    }

    setSubmitting(true);
    try {
      await rfqClient.issueQuote(threadId, {
        price_ngwee: priceNgwee,
        validity_days: days,
        message: message.trim() || undefined,
      });
      setActiveId(null);
      setAmount("");
      setMessage("");
      await loadThreads();
    } catch (err) {
      if (err instanceof ApiError && err.code === "rfq.invalid_status") {
        setFormError(t("quoteForm.invalidStatus"));
      } else {
        setFormError(t("quoteForm.submitFailed"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async (threadId: string) => {
    setSubmitting(true);
    try {
      await rfqClient.reject(threadId);
      await loadThreads();
    } catch {
      setError(t("rejectFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("loading")} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {threads.length === 0 ? (
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {threads.map((thread) => (
            <li key={thread.id} className="rounded-lg border border-border bg-surface p-4 shadow-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Badge variant="public" label={t(`status.${thread.status}` as "status.pending")} />
                <time className="text-xs text-text-3">
                  {new Date(thread.created_at).toLocaleDateString(locale)}
                </time>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm text-text">
                {thread.requested_details}
              </p>
              {thread.quote_price_ngwee ? (
                <p className="mt-2 font-mono text-sm font-semibold text-display-ink">
                  {t("yourQuote", { amount: formatK(thread.quote_price_ngwee) })}
                </p>
              ) : null}
              {thread.status === "pending" || thread.status === "quoted" ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="primary"
                    loadingLabel={t("quoteForm.submitting")}
                    onClick={() => {
                      setActiveId(activeId === thread.id ? null : thread.id);
                      setFormError(null);
                    }}
                  >
                    {activeId === thread.id ? t("quoteForm.close") : t("quoteForm.open")}
                  </Button>
                  {thread.status === "pending" ? (
                    <Button
                      type="button"
                      variant="secondary"
                      loading={submitting}
                      loadingLabel={t("quoteForm.submitting")}
                      onClick={() => void handleReject(thread.id)}
                    >
                      {t("reject")}
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {activeId === thread.id ? (
                <form
                  className="mt-4 flex flex-col gap-3 border-t border-border pt-4"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleSubmitQuote(thread.id);
                  }}
                >
                  <FormField
                    label={t("quoteForm.amountLabel")}
                    errorMessage={formError ?? undefined}
                  >
                    <Input
                      name="amount"
                      inputMode="decimal"
                      placeholder="0.00"
                      value={amount}
                      onChange={(event) => setAmount(event.target.value)}
                    />
                  </FormField>
                  <FormField label={t("quoteForm.validityLabel")}>
                    <Input
                      name="validityDays"
                      inputMode="numeric"
                      value={validityDays}
                      onChange={(event) => setValidityDays(event.target.value)}
                    />
                  </FormField>
                  <FormField label={t("quoteForm.messageLabel")}>
                    <Input
                      name="message"
                      value={message}
                      onChange={(event) => setMessage(event.target.value)}
                    />
                  </FormField>
                  <Button
                    type="submit"
                    variant="primary"
                    loading={submitting}
                    loadingLabel={t("quoteForm.submitting")}
                  >
                    {t("quoteForm.submit")}
                  </Button>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
