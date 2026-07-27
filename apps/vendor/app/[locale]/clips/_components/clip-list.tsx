"use client";

import { useSession } from "@vergeo/auth/use-session";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VendorEmptyState, VendorErrorState } from "../../_components/async-state";
import { createClipsClient, LIVE_STATUSES, type VendorClipList } from "../_lib/clips-client";

/**
 * M17-P06 — "my clips".
 *
 * The trust requirement (D-V8) is the whole reason this component is careful
 * about one thing: **a clip that is not published must never read as live.** A
 * vendor who believes an unapproved clip is public will tell customers to go
 * look at it. So status copy comes from an explicit per-status key, the "live"
 * tone is gated on `LIVE_STATUSES`, and a status this build does not recognise
 * falls through to the *awaiting* treatment rather than the green one.
 */
export function ClipList({ locale }: { locale: string }) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [data, setData] = useState<VendorClipList | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const clipsClient = useMemo(() => createClipsClient(getToken), [getToken]);

  useEffect(() => {
    if (sessionLoading) return;
    if (!session) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    clipsClient
      .list()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clipsClient, reloadKey, session, sessionLoading]);

  if (loading || sessionLoading) {
    return (
      <p role="status" className="p-4 text-sm text-muted" data-testid="clips-loading">
        {t("clips.loading")}
      </p>
    );
  }

  if (failed) {
    return (
      <VendorErrorState
        title={t("clips.error.title")}
        retryLabel={t("clips.error.retry")}
        onRetry={() => setReloadKey((key) => key + 1)}
        data-testid="clips-error"
      />
    );
  }

  const items = data?.items ?? [];
  const exhausted = (data?.remaining_this_week ?? 0) <= 0;

  return (
    <section className="flex flex-col gap-4 p-4">
      <header className="flex flex-col gap-2">
        <h1 className="text-h2 font-semibold text-text">{t("clips.title")}</h1>
        <p className="text-sm text-muted">{t("clips.intro")}</p>

        {data ? (
          <p data-testid="clips-quota" className="text-sm text-text">
            {exhausted
              ? t("clips.quota.exhausted", {
                  cap: data.weekly_cap,
                  days: data.window_days,
                })
              : t("clips.quota.label", {
                  remaining: data.remaining_this_week,
                  cap: data.weekly_cap,
                })}
          </p>
        ) : null}

        {/* The cap is server-enforced; the UI reflects it rather than granting
            an upload the API would refuse. */}
        <Link
          href={`/${locale}/clips/new`}
          aria-disabled={exhausted}
          data-testid="clips-new-link"
          className={`tap inline-flex min-h-11 w-fit items-center rounded-full px-4 py-2 text-sm font-medium ${
            exhausted
              ? "pointer-events-none border border-border bg-bg-2 text-muted"
              : "bg-primary text-surface"
          }`}
        >
          {t("clips.new")}
        </Link>
      </header>

      {items.length === 0 ? (
        <VendorEmptyState
          title={t("clips.empty.title")}
          body={t("clips.empty.body")}
          data-testid="clips-empty"
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((clip) => {
            const live = LIVE_STATUSES.has(clip.status);
            return (
              <li
                key={clip.id}
                data-testid="vendor-clip-row"
                data-clip-status={clip.status}
                className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    data-testid="vendor-clip-status"
                    className={`rounded-full px-2 py-1 text-xs font-medium ${
                      live ? "bg-success/15 text-success" : "bg-bg-2 text-text"
                    }`}
                  >
                    {t(`clips.status.${clip.status}`)}
                  </span>
                  {clip.duration_s ? (
                    <span className="text-xs text-muted">
                      {t("clips.durationSeconds", { seconds: clip.duration_s })}
                    </span>
                  ) : null}
                </div>

                <p className="text-xs text-muted" data-testid="vendor-clip-status-help">
                  {t(`clips.statusHelp.${clip.status}`)}
                </p>

                {/* Vendor caption is their own text, but it is still rendered as
                    a text node — the studio is not a place to start allowing HTML. */}
                {clip.caption ? <p className="text-sm text-text">{clip.caption}</p> : null}

                {clip.rejection_reason ? (
                  <p className="text-sm text-danger" data-testid="vendor-clip-rejection">
                    {t("clips.rejectionReason", { reason: clip.rejection_reason })}
                  </p>
                ) : null}

                <p className="text-xs text-muted">
                  {t("clips.stats.views", { count: clip.view_count })} ·{" "}
                  {t("clips.stats.likes", { count: clip.like_count })}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
