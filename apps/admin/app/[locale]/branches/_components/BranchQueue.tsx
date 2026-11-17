"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import { branchesApi, type BranchQueueItem } from "./api";

const STATUSES = ["pending_review", "info_requested", "draft", "approved", "rejected"] as const;

export function BranchQueue({ locale }: { locale: string }) {
  const t = useTranslations("admin.branches");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("pending_review");
  const [items, setItems] = useState<BranchQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await branchesApi.request<BranchQueueItem[]>(`/admin/branches?status=${status}`));
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
            onChange={(event) => setStatus(event.target.value as (typeof STATUSES)[number])}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`status.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <Link
          href={`/${locale}/branches/flags`}
          className="inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm text-text no-underline"
        >
          {t("queue.flagsLink")}
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
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <div className="min-w-0 space-y-0.5">
                <Link
                  href={`/${locale}/branches/${item.id}`}
                  className="font-medium text-primary no-underline"
                >
                  {item.display_name}
                </Link>
                <p className="m-0 text-xs text-muted">
                  {item.business_name ?? "—"} · {t(`kind.${item.branch_kind}`)} ·{" "}
                  {t("queue.evidence", { count: item.evidence_count })}
                </p>
              </div>
              {item.open_flags > 0 ? (
                <span className="rounded-pill bg-accent-tint px-2 py-0.5 text-xs font-semibold text-accent-deep">
                  {t("queue.openFlags", { count: item.open_flags })}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
