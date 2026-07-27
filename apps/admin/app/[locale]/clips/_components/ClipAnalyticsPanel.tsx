"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { adminClipsApi, type ClipAnalytics } from "./api";
import { formatUsdMicros, spendPercent } from "./cost";

/**
 * M17-P08 — the cost and conversion dashboard.
 *
 * Two questions, in this order: **are we going to get a bill**, and **is any of
 * this working**. Spend comes first on the page because it is the one that has a
 * deadline.
 *
 * The reset control is the documented operator reversal from
 * `docs/ops/clip-cost-runbook.md`. It is shown only when the guard has actually
 * tripped — a permanently visible "turn the safety off" button is an invitation.
 */
export function ClipAnalyticsPanel() {
  const t = useTranslations("admin.clips.analytics");
  const tRoot = useTranslations("admin.clips");
  const [data, setData] = useState<ClipAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      setData(await adminClipsApi.analytics());
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onReset = useCallback(async () => {
    setBusy(true);
    try {
      await adminClipsApi.resetKillSwitch();
      await load();
    } catch {
      setError(t("resetFailed"));
    } finally {
      setBusy(false);
    }
  }, [load, t]);

  if (loading) {
    return (
      <p className="text-sm text-muted" data-testid="clip-analytics-loading">
        {tRoot("loading")}
      </p>
    );
  }

  if (error && !data) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={tRoot("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  if (!data) {
    return null;
  }

  const percent = spendPercent(data.cost.spend_usd_micros, data.cost.cap_usd_micros);

  return (
    <section className="flex flex-col gap-6" data-testid="clip-analytics">
      <div className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-4">
        <h2 className="text-sm font-medium text-text">{t("costTitle")}</h2>
        <p className="text-h2 text-text" data-testid="clip-analytics-spend">
          {t("spendOfCap", {
            spend: formatUsdMicros(data.cost.spend_usd_micros),
            cap: formatUsdMicros(data.cost.cap_usd_micros),
          })}
        </p>
        <p className="text-sm text-muted">
          {t("headroom", { amount: formatUsdMicros(data.cost.headroom_usd_micros) })} ·{" "}
          {t("percentUsed", { percent })}
        </p>

        {data.cost.uploads_paused ? (
          <div
            role="alert"
            data-testid="clip-analytics-paused"
            className="mt-2 flex flex-col gap-2"
          >
            <p className="text-sm text-danger">{t("paused")}</p>
            <p className="text-xs text-muted">{t("pausedBody")}</p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void onReset()}
              data-testid="clip-analytics-reset"
              className="tap w-fit min-h-11 rounded-full border border-danger bg-surface px-4 py-2 text-sm text-danger disabled:opacity-50"
            >
              {t("reset")}
            </button>
          </div>
        ) : (
          <p className="text-sm text-success" data-testid="clip-analytics-active">
            {t("uploadsActive")}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-4">
        <h2 className="text-sm font-medium text-text">{t("funnelTitle")}</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-muted">{t("published")}</dt>
            <dd className="text-text">{data.funnel.published_clips}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("pendingReview")}</dt>
            <dd className="text-text">{data.funnel.pending_review}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("views")}</dt>
            <dd className="text-text">{data.funnel.views}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("likes")}</dt>
            <dd className="text-text">{data.funnel.likes}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("addToCarts")}</dt>
            <dd className="text-text">{data.funnel.add_to_carts}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("attributedOrders")}</dt>
            <dd className="text-text">{data.funnel.attributed_orders}</dd>
          </div>
        </dl>
        <p className="text-xs text-muted">{t("attributionNote")}</p>
      </div>
    </section>
  );
}
