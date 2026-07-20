"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, Button, Spinner } from "../../listings/new/_lib/ui";
import { createPayoutsClient } from "../_lib/payouts-client";

import type { PayoutBalances, PayoutHistoryItem } from "../_lib/payouts-client";

type PayoutsViewProps = {
  locale: string;
};

function currentMonthValue(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function statusVariant(status: string) {
  if (status === "paid") {
    return "free";
  }
  if (status === "failed") {
    return "sold_out";
  }
  if (status === "processing") {
    return "selling_fast";
  }
  return "public";
}

function statusLabel(status: string, t: ReturnType<typeof useTranslations<"vendor">>): string {
  if (status === "paid") {
    return t("payouts.history.status.paid");
  }
  if (status === "failed") {
    return t("payouts.history.status.failed");
  }
  if (status === "processing") {
    return t("payouts.history.status.processing");
  }
  return t("payouts.history.status.pending");
}

export function PayoutsView({ locale }: PayoutsViewProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [balances, setBalances] = useState<PayoutBalances | null>(null);
  const [history, setHistory] = useState<PayoutHistoryItem[]>([]);
  const [month, setMonth] = useState(currentMonthValue);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const payoutsClient = useMemo(() => createPayoutsClient(getToken), [getToken]);

  const load = useCallback(async () => {
    setError(null);
    const [balanceResult, historyResult] = await Promise.all([
      payoutsClient.getBalances(),
      payoutsClient.getHistory(),
    ]);
    setBalances(balanceResult);
    setHistory(historyResult.items);
  }, [payoutsClient]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    void load()
      .catch(() => {
        if (!cancelled) {
          setError(t("payouts.errors.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load, session, sessionLoading, t]);

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      const blob = await payoutsClient.downloadStatement(month);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `payout-statement-${month}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("payouts.errors.statementFailed"));
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("payouts.loading")} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-text-2">{t("payouts.eyebrow")}</p>
        <h1 className="font-display text-2xl font-semibold">{t("payouts.title")}</h1>
        <p className="text-sm text-text-2">{t("payouts.intro")}</p>
      </header>

      {balances?.payouts_blocked ? (
        <div
          className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm text-text"
          role="status"
        >
          <p className="font-medium">{t("payouts.hold.noticeTitle")}</p>
          <p className="mt-1">{t("payouts.hold.noticeBody")}</p>
        </div>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {balances ? (
        <section className="grid gap-3 rounded-xl border border-border bg-surface p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
            {t("payouts.balances.heading")}
          </h2>
          <div className="grid gap-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm">{t("payouts.balances.escrowHeld")}</span>
              <span className="font-mono text-base font-semibold">
                {formatK(balances.escrow_held_ngwee)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm">{t("payouts.balances.released")}</span>
              <span className="font-mono text-base font-semibold">
                {formatK(balances.released_available_ngwee)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm">{t("payouts.balances.paidOut")}</span>
              <span className="font-mono text-base font-semibold">
                {formatK(balances.paid_out_ngwee)}
              </span>
            </div>
          </div>
          <p className="text-xs text-text-3">{t("payouts.balances.ledgerNote")}</p>
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
            {t("payouts.history.heading")}
          </h2>
          <Link
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            href={`/${locale}/payouts/method`}
          >
            {t("payouts.method.link")}
          </Link>
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-text-2">{t("payouts.history.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {history.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
              >
                <div className="min-w-0">
                  <p className="font-mono text-sm font-semibold">{formatK(item.amount_ngwee)}</p>
                  <p className="truncate text-xs text-text-3">{item.lenco_reference}</p>
                </div>
                <Badge label={statusLabel(item.status, t)} variant={statusVariant(item.status)} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-3">
          {t("payouts.statement.heading")}
        </h2>
        <label className="flex flex-col gap-1 text-sm">
          <span>{t("payouts.statement.monthLabel")}</span>
          <input
            className="min-h-11 rounded-md border border-border bg-surface px-3"
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
          />
        </label>
        <Button
          disabled={downloading}
          loading={downloading}
          loadingLabel={t("payouts.statement.downloading")}
          onClick={() => void handleDownload()}
          type="button"
        >
          {t("payouts.statement.downloadCsv")}
        </Button>
        <p className="text-xs text-text-3">{t("payouts.statement.pdfStub")}</p>
      </section>
    </div>
  );
}
