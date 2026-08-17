"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { configApi, type FxRate, type FxRatesResponse } from "./api";
import { ConfirmDiffDialog } from "./ConfirmDiffDialog";

function microsToNgweePerUsd(micros: number): number {
  return Math.trunc(micros / 10_000);
}

function zmwPerUsdToMicros(value: string): number | null {
  const trimmed = value.trim().replace(/,/g, "");
  if (!/^(0|[1-9]\d*)(\.\d{1,6})?$/.test(trimmed)) {
    return null;
  }
  const [wholeRaw, fractionRaw = ""] = trimmed.split(".");
  const whole = Number(wholeRaw);
  if (!Number.isSafeInteger(whole) || whole < 0) {
    return null;
  }
  const fraction = (fractionRaw + "000000").slice(0, 6);
  const micros = whole * 1_000_000 + Number(fraction);
  if (!Number.isSafeInteger(micros) || micros <= 0) {
    return null;
  }
  return micros;
}

export function FxRateEditor() {
  const t = useTranslations("admin.config");
  const [current, setCurrent] = useState<FxRate | null>(null);
  const [history, setHistory] = useState<FxRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rateZmw, setRateZmw] = useState("");
  const [marginBps, setMarginBps] = useState("0");
  const [source, setSource] = useState("Bank of Zambia");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<FxRatesResponse>("/admin/config/fx-rates");
      setCurrent(data.current);
      setHistory(data.history);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const parsedMicros = useMemo(() => zmwPerUsdToMicros(rateZmw), [rateZmw]);
  const parsedMargin = Number(marginBps);

  const publish = async () => {
    if (parsedMicros === null || !Number.isInteger(parsedMargin) || parsedMargin < 0) {
      return;
    }
    const now = new Date();
    const expires = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    setSaving(true);
    try {
      await configApi.request("/admin/config/fx-rates", {
        method: "POST",
        body: JSON.stringify({
          rate_zmw_per_usd_micros: parsedMicros,
          vendor_margin_bps: parsedMargin,
          source: source.trim(),
          effective_at: now.toISOString(),
          expires_at: expires.toISOString(),
        }),
      });
      setConfirmOpen(false);
      setRateZmw("");
      await load();
    } catch {
      setError(t("fx.publishError"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="admin-fx-editor">
      <section className="rounded-md border border-border p-4">
        <h3 className="font-medium text-text">{t("fx.currentHeading")}</h3>
        {current ? (
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">{t("fx.rate")}</dt>
              <dd className="font-mono text-text">
                {formatK(microsToNgweePerUsd(current.rate_zmw_per_usd_micros))} / USD
              </dd>
            </div>
            <div>
              <dt className="text-muted">{t("fx.margin")}</dt>
              <dd className="font-mono text-text">{current.vendor_margin_bps} bps</dd>
            </div>
            <div>
              <dt className="text-muted">{t("fx.source")}</dt>
              <dd className="text-text">{current.source}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("fx.expires")}</dt>
              <dd className="font-mono text-text">{current.expires_at}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-sm text-muted">{t("fx.nonePublished")}</p>
        )}
        {current?.stale ? (
          <p className="mt-3 text-sm font-medium text-danger" role="status">
            {t("fx.staleWarning")}
          </p>
        ) : null}
      </section>

      <section className="space-y-3 rounded-md border border-border p-4">
        <h3 className="font-medium text-text">{t("fx.publishHeading")}</h3>
        <p className="text-sm text-muted">{t("fx.publishHelp")}</p>
        <label className="block text-sm">
          <span className="text-muted">{t("fx.rateZmw")}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 font-mono"
            inputMode="decimal"
            value={rateZmw}
            onChange={(event) => setRateZmw(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">{t("fx.margin")}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 font-mono"
            inputMode="numeric"
            value={marginBps}
            onChange={(event) => setMarginBps(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">{t("fx.source")}</span>
          <input
            className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2"
            value={source}
            onChange={(event) => setSource(event.target.value)}
          />
        </label>
        {parsedMicros ? (
          <p className="text-xs text-muted">
            {t("fx.preview", { rate: formatK(microsToNgweePerUsd(parsedMicros)) })}
          </p>
        ) : null}
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm text-white disabled:opacity-50"
          disabled={parsedMicros === null || !source.trim() || saving}
          onClick={() => setConfirmOpen(true)}
        >
          {t("fx.publish")}
        </button>
      </section>

      <section>
        <h3 className="font-medium text-text">{t("fx.historyHeading")}</h3>
        <ul className="mt-2 space-y-2">
          {history.map((row) => (
            <li key={row.id} className="rounded-md border border-border p-3 text-sm">
              <p className="font-mono">
                {formatK(microsToNgweePerUsd(row.rate_zmw_per_usd_micros))} / USD · {row.source}
              </p>
              <p className="text-xs text-muted">
                {row.effective_at} → {row.expires_at}
                {row.stale ? ` · ${t("fx.stale")}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <ConfirmDiffDialog
        open={confirmOpen}
        dangerous
        fromLabel={t("confirm.from")}
        toLabel={t("confirm.to")}
        fromValue={
          current
            ? formatK(microsToNgweePerUsd(current.rate_zmw_per_usd_micros))
            : t("fx.nonePublished")
        }
        toValue={parsedMicros ? formatK(microsToNgweePerUsd(parsedMicros)) : ""}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={publish}
      />
    </div>
  );
}
