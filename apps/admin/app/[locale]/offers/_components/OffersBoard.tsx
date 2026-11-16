"use client";

import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import {
  type AdminOffer,
  type AdminOfferFilters,
  DEFAULT_FILTERS,
  listOffers,
  OFFER_STATES,
  OFFER_STATUSES,
  OFFER_TYPES,
  setOfferPaused,
} from "./api";

type OffersBoardProps = {
  locale: string;
};

type PendingAction = {
  offer: AdminOffer;
  pause: boolean;
};

const NOTE_MAX = 500;

function formatWhen(value: string | null, locale: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString(locale);
}

export function OffersBoard({ locale }: OffersBoardProps) {
  const t = useTranslations("admin.offers");
  const [filters, setFilters] = useState<AdminOfferFilters>(DEFAULT_FILTERS);
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<AdminOffer[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const data = await listOffers(filters);
      setItems(data.items);
      setTruncated(data.truncated);
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [filters, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onActionDone = (updated: AdminOffer) => {
    setPending(null);
    setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    notify.success(updated.paused_by_admin ? t("pausedToast") : t("unpausedToast"));
  };

  return (
    <div className="space-y-4">
      <form
        className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4"
        role="search"
        aria-label={t("filters.label")}
        onSubmit={(event) => {
          event.preventDefault();
          setFilters((current) => ({ ...current, q: search }));
        }}
      >
        <label className="block text-sm text-text">
          {t("filters.state")}
          <select
            className="mt-1 min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm"
            value={filters.state}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                state: event.target.value as AdminOfferFilters["state"],
              }))
            }
          >
            <option value="all">{t("filters.all")}</option>
            {OFFER_STATES.map((value) => (
              <option key={value} value={value}>
                {t(`state.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-text">
          {t("filters.status")}
          <select
            className="mt-1 min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm"
            value={filters.status}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                status: event.target.value as AdminOfferFilters["status"],
              }))
            }
          >
            <option value="all">{t("filters.all")}</option>
            {OFFER_STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`status.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-text">
          {t("filters.type")}
          <select
            className="mt-1 min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm"
            value={filters.offerType}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                offerType: event.target.value as AdminOfferFilters["offerType"],
              }))
            }
          >
            <option value="all">{t("filters.all")}</option>
            {OFFER_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`type.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-text">
          {t("filters.search")}
          <span className="mt-1 flex gap-2">
            <input
              type="search"
              className="min-h-11 w-full min-w-0 rounded-md border border-border bg-surface px-3 text-sm"
              value={search}
              maxLength={120}
              placeholder={t("filters.searchPlaceholder")}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md border border-primary px-3 text-sm text-primary"
            >
              {t("filters.apply")}
            </button>
          </span>
        </label>
      </form>

      {loading ? <p className="text-sm text-muted">{t("loading")}</p> : null}

      {!loading && error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={error}
          hint={permissionDenied ? t("permissionDeniedHint") : undefined}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : null}

      {!loading && !error && items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : null}

      {!loading && !error && items.length > 0 ? (
        <ul className="space-y-3" aria-label={t("listLabel")}>
          {items.map((offer) => {
            const starts = formatWhen(offer.starts_at, locale);
            const ends = formatWhen(offer.ends_at, locale);
            return (
              <li
                key={offer.id}
                className="rounded-lg border border-border bg-surface p-4 shadow-sm"
                data-testid="admin-offer"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-medium uppercase tracking-wide text-muted">
                        {t(`type.${offer.offer_type}`)}
                      </span>
                      <span className="rounded-full border border-border px-2 py-0.5 text-muted">
                        {t(`status.${offer.status}`)}
                      </span>
                      {offer.paused_by_admin ? (
                        <span className="rounded-full bg-danger/10 px-2 py-0.5 font-medium text-danger">
                          {t("state.admin_paused")}
                        </span>
                      ) : offer.live ? (
                        <span className="rounded-full bg-success/10 px-2 py-0.5 font-medium text-success">
                          {t("state.live")}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="break-words font-medium text-text">{offer.title}</h2>
                    <p className="text-sm text-muted">
                      {t("vendor", { name: offer.vendor_name ?? offer.vendor_id })}
                    </p>
                    <p className="text-xs text-muted">
                      {ends
                        ? t("window", { starts: starts ?? "", ends })
                        : t("windowOpen", { starts: starts ?? "" })}
                    </p>
                    <p className="text-xs text-muted">
                      {offer.per_customer_limit
                        ? t("perCustomer", { count: offer.per_customer_limit })
                        : t("perCustomerUnlimited")}
                      {offer.gift_stock_total !== null
                        ? ` · ${t("giftStock", {
                            reserved: offer.gift_stock_reserved,
                            total: offer.gift_stock_total,
                          })}`
                        : ""}
                    </p>
                    {offer.admin_note ? (
                      <p className="break-words text-xs text-text">
                        {t("note", { note: offer.admin_note })}
                      </p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
                      offer.paused_by_admin
                        ? "border-primary text-primary"
                        : "border-danger text-danger"
                    }`}
                    onClick={() => setPending({ offer, pause: !offer.paused_by_admin })}
                  >
                    {offer.paused_by_admin ? t("actions.unpause") : t("actions.pause")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      {truncated ? <p className="text-xs text-muted">{t("truncated")}</p> : null}

      {pending ? (
        <PauseDialog
          offer={pending.offer}
          pause={pending.pause}
          onClose={() => setPending(null)}
          onDone={onActionDone}
        />
      ) : null}
    </div>
  );
}

type PauseDialogProps = {
  offer: AdminOffer;
  pause: boolean;
  onClose: () => void;
  onDone: (offer: AdminOffer) => void;
};

export function PauseDialog({ offer, pause, onClose, onDone }: PauseDialogProps) {
  const t = useTranslations("admin.offers");
  const [note, setNote] = useState(pause ? "" : (offer.admin_note ?? ""));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const trimmed = note.trim().slice(0, NOTE_MAX);
      onDone(await setOfferPaused(offer.id, pause, trimmed || null));
    } catch {
      setError(t("actions.failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="offer-pause-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-4 shadow-lg">
        <h2 id="offer-pause-title" className="font-serif text-lg text-text">
          {pause ? t("actions.pauseTitle") : t("actions.unpauseTitle")}
        </h2>
        <p className="mt-2 break-words text-sm text-muted">
          {pause
            ? t("actions.pauseBody", { title: offer.title })
            : t("actions.unpauseBody", { title: offer.title })}
        </p>
        <label className="mt-4 block text-sm text-text">
          {t("actions.noteLabel")}
          <textarea
            className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
            rows={3}
            maxLength={NOTE_MAX}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={t("actions.notePlaceholder")}
          />
        </label>
        <p className="mt-1 text-xs text-muted">{t("actions.audited")}</p>
        {error ? (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            onClick={onClose}
            disabled={submitting}
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            data-testid="offer-pause-confirm"
            className={`inline-flex min-h-11 items-center rounded-md px-4 text-sm font-medium text-white ${
              pause ? "bg-danger" : "bg-primary"
            }`}
            onClick={() => void submit()}
            disabled={submitting}
          >
            {submitting
              ? t("actions.submitting")
              : pause
                ? t("actions.confirmPause")
                : t("actions.confirmUnpause")}
          </button>
        </div>
      </div>
    </div>
  );
}
