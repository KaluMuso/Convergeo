"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../lib/api-base-url";
import { VendorPage } from "../_components/vendor-page";
import { ListSkeleton } from "../_components/vendor-skeletons";
import { formatOrderCode } from "../_lib/order-code";
import { createManageClient } from "../listings/[id]/edit/_lib/manage-client";
import { Badge, Button, FormField, Input } from "../listings/new/_lib/ui";
import { createServicesClient } from "../services/_lib/services-client";

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

type QuoteDraft = {
  amount: string;
  message: string;
  validityDays: string;
};

const EMPTY_DRAFT: QuoteDraft = { amount: "", message: "", validityDays: "7" };

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

function rfqStatusLabel(
  status: string,
  t: ReturnType<typeof useTranslations<"vendor.rfq">>,
  tR: ReturnType<typeof useTranslations<"vendor.requests.rfq">>,
): string {
  const legacyKey = `status.${status}` as "status.pending";
  if (t.has(legacyKey)) {
    return t(legacyKey);
  }
  const key = `status.${status}` as "status.expired";
  if (tR.has(key)) {
    return tR(key);
  }
  return tR("status.unknown", { status });
}

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default function VendorRfqPage({ params }: PageProps) {
  const [locale, setLocale] = useState("en");
  const t = useTranslations("vendor.rfq");
  const tR = useTranslations("vendor.requests.rfq");
  const { session, loading: sessionLoading } = useSession();
  const [threads, setThreads] = useState<RfqThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, QuoteDraft>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [listingTitles, setListingTitles] = useState<Record<string, string>>({});
  const [serviceTitles, setServiceTitles] = useState<Record<string, string>>({});

  useEffect(() => {
    void params.then(({ locale: nextLocale }) => setLocale(nextLocale));
  }, [params]);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const rfqClient = useMemo(() => createRfqVendorClient(getToken), [getToken]);
  const listingsClient = useMemo(() => createManageClient(getToken), [getToken]);
  const servicesClient = useMemo(() => createServicesClient(getToken), [getToken]);

  const loadSubjectTitles = useCallback(
    async (items: RfqThread[]) => {
      const listingIds = new Set(items.map((row) => row.listing_id).filter(Boolean) as string[]);
      const serviceIds = new Set(items.map((row) => row.service_id).filter(Boolean) as string[]);
      if (listingIds.size === 0 && serviceIds.size === 0) {
        return;
      }
      try {
        const [listings, services] = await Promise.all([
          listingIds.size > 0 ? listingsClient.listListings() : Promise.resolve([]),
          serviceIds.size > 0
            ? servicesClient.listServices().then((r) => r.items)
            : Promise.resolve([]),
        ]);
        const nextListings: Record<string, string> = {};
        for (const row of listings) {
          if (listingIds.has(row.id)) {
            nextListings[row.id] = row.title;
          }
        }
        const nextServices: Record<string, string> = {};
        for (const row of services) {
          if (serviceIds.has(row.id)) {
            nextServices[row.id] = row.title;
          }
        }
        setListingTitles(nextListings);
        setServiceTitles(nextServices);
      } catch {
        // Subject titles are supplemental; the queue still works without them.
      }
    },
    [listingsClient, servicesClient],
  );

  const loadThreads = useCallback(async () => {
    setLoading(true);
    try {
      const response = await rfqClient.listThreads();
      setThreads(response.items);
      setError(null);
      await loadSubjectTitles(response.items);
    } catch {
      setError(t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [loadSubjectTitles, rfqClient, t]);

  useEffect(() => {
    if (!sessionLoading && session?.access_token) {
      void loadThreads();
    }
  }, [loadThreads, session?.access_token, sessionLoading]);

  const draftFor = (threadId: string): QuoteDraft => drafts[threadId] ?? EMPTY_DRAFT;

  const patchDraft = (threadId: string, patch: Partial<QuoteDraft>) => {
    setDrafts((current) => ({
      ...current,
      [threadId]: { ...draftFor(threadId), ...patch },
    }));
  };

  const subjectLabel = (thread: RfqThread): string | null => {
    if (thread.listing_id && listingTitles[thread.listing_id]) {
      return listingTitles[thread.listing_id]!;
    }
    if (thread.service_id && serviceTitles[thread.service_id]) {
      return serviceTitles[thread.service_id]!;
    }
    if (thread.listing_id) {
      return tR("unknownListing");
    }
    if (thread.service_id) {
      return tR("unknownService");
    }
    return null;
  };

  const handleSubmitQuote = async (threadId: string) => {
    setFormError(null);
    const draft = draftFor(threadId);
    let priceNgwee: number;
    try {
      priceNgwee = zmwDecimalToNgwee(draft.amount);
    } catch {
      setFormError(t("quoteForm.invalidAmount"));
      return;
    }
    if (priceNgwee <= 0) {
      setFormError(t("quoteForm.invalidAmount"));
      return;
    }
    const days = Number.parseInt(draft.validityDays, 10);
    if (!Number.isFinite(days) || days < 1) {
      setFormError(t("quoteForm.invalidValidity"));
      return;
    }

    setSubmittingId(threadId);
    try {
      await rfqClient.issueQuote(threadId, {
        price_ngwee: priceNgwee,
        validity_days: days,
        message: draft.message.trim() || undefined,
      });
      setActiveId(null);
      setDrafts((current) => ({ ...current, [threadId]: EMPTY_DRAFT }));
      await loadThreads();
    } catch (err) {
      if (err instanceof ApiError && err.code === "rfq.invalid_status") {
        setFormError(t("quoteForm.invalidStatus"));
      } else {
        setFormError(t("quoteForm.submitFailed"));
      }
    } finally {
      setSubmittingId(null);
    }
  };

  const handleReject = async (threadId: string) => {
    if (!window.confirm(tR("declineConfirm"))) {
      return;
    }
    setSubmittingId(threadId);
    try {
      await rfqClient.reject(threadId);
      await loadThreads();
    } catch {
      setError(t("rejectFailed"));
    } finally {
      setSubmittingId(null);
    }
  };

  if (sessionLoading || loading) {
    return (
      <VendorPage width="full">
        <ListSkeleton label={t("loading")} />
      </VendorPage>
    );
  }

  return (
    <VendorPage width="full">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {threads.length === 0 ? (
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {threads.map((thread) => {
            const draft = draftFor(thread.id);
            const submitting = submittingId === thread.id;
            const subject = subjectLabel(thread);
            const canQuote = thread.status === "pending" || thread.status === "quoted";

            return (
              <li
                key={thread.id}
                className="rounded-lg border border-border bg-surface p-4 shadow-1"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant="public" label={rfqStatusLabel(thread.status, t, tR)} />
                  <time className="text-sm text-text-3" dateTime={thread.created_at}>
                    {new Date(thread.created_at).toLocaleDateString(locale)}
                  </time>
                </div>
                {subject ? (
                  <p className="mt-2 text-sm font-medium text-display-ink">{subject}</p>
                ) : null}
                <p className="mt-1 text-sm text-text-2">
                  {tR("buyerRef", { ref: formatOrderCode(thread.customer_id) })}
                </p>
                {thread.quote_valid_until ? (
                  <p className="mt-1 text-sm text-text-2">
                    {tR("validUntil", {
                      date: new Date(thread.quote_valid_until).toLocaleDateString(locale),
                    })}
                  </p>
                ) : null}
                <p className="mt-3 whitespace-pre-wrap text-sm text-text">
                  {thread.requested_details}
                </p>
                {thread.quote_price_ngwee ? (
                  <p className="mt-2 font-mono text-sm font-semibold text-display-ink">
                    {t("yourQuote", { amount: formatK(thread.quote_price_ngwee) })}
                  </p>
                ) : null}
                {canQuote ? (
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
                        loadingLabel={tR("declining")}
                        disabled={submitting}
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
                        placeholder={t("quoteForm.amountPlaceholder")}
                        value={draft.amount}
                        onChange={(event) => patchDraft(thread.id, { amount: event.target.value })}
                      />
                    </FormField>
                    <FormField label={t("quoteForm.validityLabel")}>
                      <Input
                        name="validityDays"
                        inputMode="numeric"
                        value={draft.validityDays}
                        onChange={(event) =>
                          patchDraft(thread.id, { validityDays: event.target.value })
                        }
                      />
                    </FormField>
                    <FormField label={t("quoteForm.messageLabel")}>
                      <Input
                        name="message"
                        value={draft.message}
                        onChange={(event) => patchDraft(thread.id, { message: event.target.value })}
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
            );
          })}
        </ul>
      )}
    </VendorPage>
  );
}
