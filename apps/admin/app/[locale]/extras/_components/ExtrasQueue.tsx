"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  REQUEST_STATUSES,
  adminActions,
  extrasApi,
  transitionBody,
  type ExtrasRequest,
  type RequestStatus,
  type TransitionTo,
} from "./api";

export function ExtrasQueue({ locale }: { locale: string }) {
  const t = useTranslations("admin.extras");
  const [status, setStatus] = useState<RequestStatus>("requested");
  const [items, setItems] = useState<ExtrasRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(
        await extrasApi.request<ExtrasRequest[]>(
          `/admin/extras/requests?status=${status}`,
        ),
      );
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(`queue.${failure.messageKey}`));
    } finally {
      setLoading(false);
    }
  }, [status, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-text-2">
          {t("queue.filter")}
          <select
            className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
            value={status}
            onChange={(event) => setStatus(event.target.value as RequestStatus)}
          >
            {REQUEST_STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`status.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <Link
          href={`/${locale}/extras/catalogue`}
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm text-text no-underline"
        >
          {t("queue.catalogueLink")}
        </Link>
      </div>
      {loading ? (
        <LoadingBlock label={t("queue.loading")} />
      ) : error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={error}
          retryLabel={t("queue.retry")}
          onRetry={() => void load()}
        />
      ) : items.length === 0 ? (
        <EmptyBlock title={t("queue.empty")} />
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

function RequestRow({
  item,
  onDone,
}: {
  item: ExtrasRequest;
  onDone: () => void;
}) {
  const t = useTranslations("admin.extras");
  const [quote, setQuote] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const actions = adminActions(item.status);

  async function act(to: TransitionTo) {
    const body = transitionBody(to, quote, note);
    if (!body) {
      setMessage(t("errors.quoteRequired"));
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await extrasApi.request(`/admin/extras/requests/${item.id}/transition`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      onDone();
    } catch {
      setMessage(t("errors.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 p-3" data-testid={`extras-request-${item.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="m-0 font-medium text-text">
          {item.extra_name ?? item.extra_key} ·{" "}
          {item.vendor_name ?? item.vendor_id}
        </p>
        <span className="text-xs text-muted">
          {t(`status.${item.status}`)}
          {item.quoted_price_ngwee !== null
            ? ` · ${t("queue.quoted", { price: formatK(item.quoted_price_ngwee) })}`
            : ""}
        </span>
      </div>
      <p className="m-0 text-xs text-muted">
        {t("queue.quantity", { count: item.quantity })}
        {item.note ? ` · ${t("queue.vendorNote", { note: item.note })}` : ""}
      </p>
      {actions.length > 0 ? (
        <div className="flex flex-wrap items-end gap-2">
          {actions.includes("quoted") ? (
            <label className="flex flex-col gap-1 text-xs text-text-2">
              {t("queue.quoteLabel")}
              <input
                inputMode="decimal"
                className="min-h-11 w-32 rounded-md border border-border bg-surface px-2 text-sm text-text"
                value={quote}
                onChange={(event) => setQuote(event.target.value)}
              />
            </label>
          ) : null}
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-text-2">
            {t("queue.noteLabel")}
            <input
              className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
              value={note}
              maxLength={1000}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {actions.map((to) => (
            <button
              key={to}
              type="button"
              disabled={busy}
              onClick={() => void act(to)}
              className="min-h-11 rounded-md border border-border px-3 text-sm text-text hover:border-primary disabled:opacity-60"
            >
              {t(`actions.${to}`)}
            </button>
          ))}
        </div>
      ) : null}
      {message ? (
        <p role="alert" className="m-0 text-xs text-danger">
          {message}
        </p>
      ) : null}
    </li>
  );
}
