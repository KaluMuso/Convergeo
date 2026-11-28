"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  CLAIM_FILTERS,
  claimsApi,
  decisionBody,
  decisionsFor,
  type AdminClaim,
  type ClaimDecision,
  type ClaimStatus,
} from "./api";

export function MadeInZambiaQueue() {
  const t = useTranslations("admin.madeInZambia");
  const [status, setStatus] = useState<ClaimStatus>("claimed");
  const [items, setItems] = useState<AdminClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(
        await claimsApi.request<AdminClaim[]>(`/admin/made-in-zambia-claims?status=${status}`),
      );
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
          onChange={(event) => setStatus(event.target.value as ClaimStatus)}
        >
          {CLAIM_FILTERS.map((value) => (
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
            <ClaimRow key={item.listing_id} item={item} onDone={() => void load()} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ClaimRow({ item, onDone }: { item: AdminClaim; onDone: () => void }) {
  const t = useTranslations("admin.madeInZambia");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const decisions = decisionsFor(item.status);

  async function decide(decision: ClaimDecision) {
    setBusy(true);
    setMessage(null);
    try {
      await claimsApi.request(`/admin/made-in-zambia-claims/${item.listing_id}/decision`, {
        method: "POST",
        body: JSON.stringify(decisionBody(decision, note)),
      });
      onDone();
    } catch (err) {
      const key = (err as { details?: { message_key?: string } } | null)?.details?.message_key;
      setMessage(
        key === "admin.madeInZambia.errors.invalidTransition"
          ? t("errors.invalidTransition")
          : t("errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 p-3" data-testid={`miz-claim-${item.listing_id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="m-0 font-medium text-text">{item.title}</p>
        <span className="text-xs text-muted">{t(`status.${item.status}`)}</span>
      </div>
      <p className="m-0 text-xs text-muted">
        {t("claim.by", { vendor: item.vendor_name ?? item.vendor_id })}
        {item.claimed_at
          ? ` · ${t("claim.claimedAt", { date: new Date(item.claimed_at).toLocaleDateString() })}`
          : ""}
      </p>
      <p className="m-0 text-sm text-text-2">
        {item.reference ? t("claim.reference", { ref: item.reference }) : t("claim.noReference")}
      </p>
      {item.reviewed_at ? (
        <p className="m-0 text-xs text-muted">
          {t("claim.reviewedAt", {
            date: new Date(item.reviewed_at).toLocaleDateString(),
          })}
          {item.review_note ? ` · ${t("claim.note", { note: item.review_note })}` : ""}
        </p>
      ) : null}
      {decisions.length > 0 ? (
        <>
          <label className="flex flex-col gap-1 text-xs text-text-2">
            {t("noteLabel")}
            <input
              maxLength={500}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {decisions.map((decision) => (
              <button
                key={decision}
                type="button"
                disabled={busy}
                onClick={() => void decide(decision)}
                className="min-h-11 rounded-md border border-border px-3 text-sm text-text hover:border-primary disabled:opacity-60"
              >
                {decision === "approve"
                  ? t("actions.approve")
                  : item.status === "approved"
                    ? t("actions.revoke")
                    : t("actions.reject")}
              </button>
            ))}
          </div>
        </>
      ) : null}
      {message ? (
        <p role="alert" className="m-0 text-xs text-danger">
          {message}
        </p>
      ) : null}
    </li>
  );
}
