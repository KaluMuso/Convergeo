"use client";

import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { createManageClient, StockAdjustment, StockContext } from "../_lib/manage-client";

type Props = {
  listingId: string;
  ownerId: string;
  client: ReturnType<typeof createManageClient>;
};

export function StockEditor({ listingId, ownerId, client }: Props) {
  const t = useTranslations("vendor.listings.manage.stock");
  const [stock, setStock] = useState<StockContext | null>(null);
  const [location, setLocation] = useState("");
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<StockAdjustment | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const storageKey = `stock-adjustment:${ownerId}:${listingId}`;

  const refresh = useCallback(async () => {
    try {
      setStock(await client.getStock(listingId));
      return true;
    } catch {
      setError(t("loadFailed"));
      return false;
    }
  }, [client, listingId, t]);

  useEffect(() => {
    void refresh();
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const operation = JSON.parse(saved) as StockAdjustment;
        setPending(operation);
        setLocation(operation.location_id ?? "");
        setDelta(String(operation.delta));
        setReason(operation.reason);
        setError(t("retrySame"));
      }
    } catch {
      setError(t("storageFailed"));
    }
  }, [refresh, storageKey, t]);

  async function submit() {
    if (!stock || busy) return;
    setError(null);
    setMessage(null);
    const quantity = Number(delta);
    if (
      !pending &&
      (!/^-?[1-9]\d*$/.test(delta) ||
        !Number.isSafeInteger(quantity) ||
        Math.abs(quantity) > 999999 ||
        !reason.trim() ||
        (stock.branch_tracked &&
          !stock.branches.some((b) => b.location_id === location && b.active)))
    ) {
      setError(t("invalid"));
      return;
    }
    const operation = pending ?? {
      operation_id: crypto.randomUUID(),
      location_id: stock.branch_tracked ? location : null,
      delta: quantity,
      reason: reason.trim(),
      sale_unit: stock.sale_unit,
      unit_step_milli: stock.unit_step_milli,
    };
    // Persist before sending: a reload or lost response must replay the exact
    // request, never issue another delta under a fresh operation ID.
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(operation));
    } catch {
      setError(t("storageFailed"));
      return;
    }
    setPending(operation);
    setBusy(true);
    try {
      const outcome = await client.adjustStock(listingId, operation);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setDelta("");
      setReason("");
      setMessage(
        t("saved", { old: outcome.old_qty, next: outcome.new_qty, id: outcome.operation_id }),
      );
      await refresh();
    } catch (caught) {
      if (caught instanceof ApiError && [403, 409, 422].includes(caught.status)) {
        // Definitive rejection: refresh before preparing a NEW operation.
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          setError(t("storageFailed"));
          return;
        }
        setPending(null);
        setStock(null);
        setError(t("conflict"));
        await refresh();
      } else {
        setError(t("retrySame"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      id="stock"
      className="space-y-3 rounded-lg border border-border p-3"
      aria-label={t("heading")}
    >
      <h2 className="font-medium">{t("heading")}</h2>
      <p>{t("help")}</p>
      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <button type="button" disabled={busy} onClick={() => void refresh()}>
        {t("refresh")}
      </button>
      {stock?.stock_mode === "tracked" ? (
        <>
          <p>{t("units", { unit: stock.sale_unit, step: stock.unit_step_milli })}</p>
          <fieldset disabled={busy || pending !== null} className="space-y-2">
            {stock.branch_tracked ? (
              <label>
                {t("branch")}
                <select value={location} onChange={(event) => setLocation(event.target.value)}>
                  <option value="">{t("choose")}</option>
                  {stock.branches.map((branch) => (
                    <option
                      key={branch.location_id}
                      value={branch.location_id}
                      disabled={!branch.active}
                    >
                      {branch.label ?? branch.location_id} — {branch.stock_qty}
                      {!branch.active ? ` (${t("inactive")})` : ""}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p>{t("pooled", { qty: stock.stock_qty ?? 0 })}</p>
            )}
            <label>
              {t("delta")}
              <input
                value={delta}
                inputMode="numeric"
                onChange={(event) => setDelta(event.target.value)}
              />
            </label>
            <label>
              {t("reason")}
              <input
                value={reason}
                maxLength={240}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          </fieldset>
          <button type="button" disabled={busy} onClick={() => void submit()}>
            {pending ? t("retry") : t("apply")}
          </button>
        </>
      ) : stock ? (
        <p>{t("notTracked")}</p>
      ) : null}
    </section>
  );
}
