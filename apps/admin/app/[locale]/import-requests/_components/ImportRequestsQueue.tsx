"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  EMPTY_DRAFT,
  STATUS_FILTERS,
  canQuote,
  draftTotal,
  importApi,
  quoteBody,
  statusActions,
  type AdminImportRequest,
  type ImportStatus,
  type QuoteDraft,
} from "./api";

export function ImportRequestsQueue() {
  const t = useTranslations("admin.importRequests");
  const [status, setStatus] = useState<ImportStatus | "all">("submitted");
  const [items, setItems] = useState<AdminImportRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query = status === "all" ? "" : `?status=${status}`;
      setItems(await importApi.request<AdminImportRequest[]>(`/admin/import-requests${query}`));
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t("errors.load"));
    } finally {
      setLoading(false);
    }
  }, [status, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm text-text-2">
        {t("filterLabel")}
        <select
          className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
          value={status}
          onChange={(event) => setStatus(event.target.value as ImportStatus | "all")}
        >
          <option value="all">{t("all")}</option>
          {STATUS_FILTERS.map((value) => (
            <option key={value} value={value}>
              {t(`status.${value}`)}
            </option>
          ))}
        </select>
      </label>
      {loading ? (
        <LoadingBlock label={t("loading")} />
      ) : error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={error}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : items.length === 0 ? (
        <EmptyBlock title={t("empty")} />
      ) : (
        <ul className="m-0 list-none divide-y divide-border rounded-md border border-border bg-surface p-0">
          {items.map((item) => (
            <RequestRow key={item.id} item={item} onDone={() => void load()} />
          ))}
        </ul>
      )}
    </div>
  );
}

const LINES = ["product", "freight", "duty", "clearing", "other"] as const;

function RequestRow({ item, onDone }: { item: AdminImportRequest; onDone: () => void }) {
  const t = useTranslations("admin.importRequests");
  const [draft, setDraft] = useState<QuoteDraft>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const total = draftTotal(draft);

  async function post(path: string, body: unknown) {
    setBusy(true);
    setMessage(null);
    try {
      await importApi.request(`/admin/import-requests/${item.id}/${path}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onDone();
    } catch (err) {
      const key = (err as { details?: { message_key?: string } } | null)?.details?.message_key;
      setMessage(
        key === "admin.importRequests.errors.invalidTransition"
          ? t("errors.invalidTransition")
          : t("errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  function sendQuote() {
    const body = quoteBody(draft);
    if (body === null) {
      setMessage(t("errors.amount"));
      return;
    }
    void post("quotes", body);
  }

  const field = (key: keyof QuoteDraft) => ({
    value: draft[key],
    onChange: (event: { target: { value: string } }) =>
      setDraft((current) => ({ ...current, [key]: event.target.value })),
  });

  return (
    <li className="space-y-2 p-3" data-testid={`import-request-${item.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="m-0 font-medium text-text">{item.title}</p>
        <span className="text-xs text-muted">{t(`status.${item.status}`)}</span>
      </div>
      <p className="m-0 text-xs text-muted">
        {t("request.by", { vendor: item.vendor_name ?? item.vendor_id })} ·{" "}
        {t("request.qty", { qty: item.quantity, unit: item.unit })}
        {item.target_unit_price_ngwee !== null
          ? ` · ${t("request.target", { price: formatK(item.target_unit_price_ngwee) })}`
          : ""}
      </p>
      {item.description ? <p className="m-0 text-sm text-text-2">{item.description}</p> : null}
      {item.reference_url ? (
        <a
          href={item.reference_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary underline"
        >
          {t("request.link")}
        </a>
      ) : null}
      <p className="m-0 text-xs text-muted">
        {item.latest_quote
          ? t("request.latest", {
              total: formatK(item.latest_quote.total_ngwee),
            })
          : t("request.noQuote")}
      </p>

      {canQuote(item.status) ? (
        <fieldset className="space-y-2 rounded-md border border-border p-3">
          <legend className="px-1 text-sm font-medium text-text">{t("form.title")}</legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {LINES.map((line) => (
              <label key={line} className="flex flex-col gap-1 text-xs text-text-2">
                {t(`form.${line}`)}
                <input
                  inputMode="decimal"
                  className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
                  {...field(line)}
                />
              </label>
            ))}
            <label className="flex flex-col gap-1 text-xs text-text-2">
              {t("form.leadTime")}
              <input
                inputMode="numeric"
                className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
                {...field("leadTime")}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-text-2">
              {t("form.validUntil")}
              <input
                type="date"
                className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
                {...field("validUntil")}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-text-2">
              {t("form.partner")}
              <input
                maxLength={80}
                className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
                {...field("partner")}
              />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-xs text-text-2">
            {t("form.notes")}
            <input
              maxLength={2000}
              className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
              {...field("notes")}
            />
          </label>
          <p className="m-0 text-xs text-muted">
            {t("form.total")}: {total === null ? "-" : formatK(total)} · {t("form.estimateOnly")}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={sendQuote}
            className="min-h-11 rounded-md border border-border px-3 text-sm text-text hover:border-primary disabled:opacity-60"
          >
            {t("actions.quote")}
          </button>
        </fieldset>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {statusActions(item.status).map((to) => (
          <button
            key={to}
            type="button"
            disabled={busy}
            onClick={() => void post("status", { to })}
            className="min-h-11 rounded-md border border-border px-3 text-sm text-text hover:border-primary disabled:opacity-60"
          >
            {to === "in_review" ? t("actions.review") : t("actions.close")}
          </button>
        ))}
      </div>
      {message ? (
        <p role="alert" className="m-0 text-xs text-danger">
          {message}
        </p>
      ) : null}
    </li>
  );
}
