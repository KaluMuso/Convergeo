"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { adminClipsApi, type ClipQueueItem } from "./api";

/**
 * M17-P07 — the pending-review queue.
 *
 * Oldest first, which is the whole point of a review target: newest-first
 * quietly starves the clips that have waited longest, which are exactly the ones
 * the 24-hour SLO is about. The API returns them in that order and this
 * component does not re-sort them.
 *
 * Posters only — no `<video>` here. Loading twenty clips to skim a queue would
 * cost the reviewer's connection for no benefit; the preview lives on the detail
 * page, behind short-lived links.
 */
export function ClipQueue({ locale }: { locale: string }) {
  const t = useTranslations("admin.clips.queue");
  const tRoot = useTranslations("admin.clips");
  const [items, setItems] = useState<ClipQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const result = await adminClipsApi.queue();
      setItems(result.items);
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

  if (loading) {
    return (
      <p className="text-sm text-muted" data-testid="admin-clips-loading">
        {tRoot("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={tRoot("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  if (items.length === 0) {
    return (
      <div
        data-testid="admin-clips-empty"
        className="rounded-lg border border-dashed border-border p-6 text-center"
      >
        <p className="font-medium text-text">{tRoot("empty.title")}</p>
        <p className="mt-1 text-sm text-muted">{tRoot("empty.body")}</p>
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-3" data-testid="admin-clips-queue">
      {items.map((item) => (
        <li
          key={item.clip_id}
          data-testid="admin-clip-row"
          data-sla-breached={item.sla_breached ? "true" : "false"}
          className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-text">
              {t("vendor")}: {item.vendor_name ?? item.vendor_id}
            </span>
            <span
              data-testid="admin-clip-age"
              className={`rounded-full px-2 py-1 text-xs ${
                item.sla_breached ? "bg-danger/15 text-danger" : "bg-bg-2 text-muted"
              }`}
            >
              {item.sla_breached
                ? t("slaBreached")
                : t("age", { hours: Math.round(item.age_hours) })}
            </span>
            <span className="rounded-full bg-bg-2 px-2 py-1 text-xs text-muted">
              {t("repeatOffender", { count: item.repeat_offender_count })}
            </span>
            {!item.media_ready ? (
              <span
                data-testid="admin-clip-media-warning"
                className="rounded-full bg-warning/15 px-2 py-1 text-xs text-warning"
              >
                {t("mediaNotReady")}
              </span>
            ) : null}
          </div>

          {/* Vendor caption is untrusted text and is rendered as a text node. */}
          {item.caption ? <p className="text-sm text-text">{item.caption}</p> : null}

          <Link
            href={`/${locale}/clips/${item.clip_id}`}
            data-testid="admin-clip-open"
            className="tap w-fit rounded-full bg-primary px-4 py-2 text-sm font-medium text-surface"
          >
            {t("open")}
          </Link>
        </li>
      ))}
    </ul>
  );
}
