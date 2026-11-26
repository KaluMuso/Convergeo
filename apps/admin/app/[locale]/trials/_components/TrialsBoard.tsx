"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";
import { extrasApi, trialEndFromDate, type TrialRow } from "../../extras/_components/api";

export function TrialsBoard() {
  const t = useTranslations("admin.trials");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<TrialRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const q = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
      setItems(await extrasApi.request<TrialRow[]>(`/admin/trials${q}`));
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    }
  }, [query, t]);

  useEffect(() => {
    void load();
    // Load once; later reloads happen on explicit search only.
  }, []);

  return (
    <div className="space-y-3">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void load();
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("search")}
          <input
            className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
            value={query}
            maxLength={80}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="min-h-11 rounded-md border border-border px-3 text-sm text-text"
        >
          {t("searchAction")}
        </button>
      </form>
      {error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={error}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : items === null ? (
        <LoadingBlock label={t("loading")} />
      ) : items.length === 0 ? (
        <EmptyBlock title={t("empty")} />
      ) : (
        <ul className="m-0 list-none divide-y divide-border rounded-md border border-border bg-surface p-0">
          {items.map((row) => (
            <TrialRowView key={row.business_id} row={row} onDone={() => void load()} />
          ))}
        </ul>
      )}
    </div>
  );
}

function TrialRowView({ row, onDone }: { row: TrialRow; onDone: () => void }) {
  const t = useTranslations("admin.trials");
  const locale = useLocale();
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const ends = row.trial_ends_at
    ? new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeZone: "Africa/Lusaka",
      }).format(new Date(row.trial_ends_at))
    : "—";

  async function change(action: "extend" | "end") {
    const endsAt = action === "extend" ? trialEndFromDate(date) : null;
    if ((action === "extend" && !endsAt) || reason.trim().length < 3) {
      setMessage(t("errors.input"));
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await extrasApi.request(`/admin/trials/${row.business_id}`, {
        method: "POST",
        body: JSON.stringify(
          action === "extend"
            ? { action, ends_at: endsAt, reason: reason.trim() }
            : { action, reason: reason.trim() },
        ),
      });
      onDone();
    } catch {
      setMessage(t("errors.failed"));
    } finally {
      setBusy(false);
    }
  }

  const input = "min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text";
  return (
    <li className="space-y-2 p-3" data-testid={`trial-${row.business_id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="m-0 font-medium text-text">{row.legal_name}</p>
        <span className="text-xs text-muted">
          {row.in_trial ? t("endsOn", { date: ends }) : t("endedOn", { date: ends })}
        </span>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("newEnd")}
          <input
            type="date"
            className={input}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label className="flex min-w-[min(100%,10rem)] flex-1 flex-col gap-1 text-xs text-text-2">
          {t("reason")}
          <input
            className={input}
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void change("extend")}
          className="min-h-11 rounded-md border border-border px-3 text-sm text-text disabled:opacity-60"
        >
          {t("extend")}
        </button>
        {row.in_trial ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void change("end")}
            className="min-h-11 rounded-md border border-border px-3 text-sm text-danger disabled:opacity-60"
          >
            {t("end")}
          </button>
        ) : null}
      </div>
      {message ? (
        <p role="alert" className="m-0 text-xs text-danger">
          {message}
        </p>
      ) : null}
    </li>
  );
}
