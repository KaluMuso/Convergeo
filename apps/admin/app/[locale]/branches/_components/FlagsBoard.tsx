"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { LoadingBlock } from "../../_components/StateBlocks";

import { branchesApi, type BranchFlag } from "./api";
import { FlagList } from "./FlagList";

const STATUSES = ["open", "cleared", "confirmed"] as const;

export function FlagsBoard() {
  const t = useTranslations("admin.branches");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("open");
  const [flags, setFlags] = useState<BranchFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFlags(await branchesApi.request<BranchFlag[]>(`/admin/branches/flags?status=${status}`));
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
      <label className="flex items-center gap-2 text-sm text-text-2">
        {t("queue.filter")}
        <select
          className="min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text"
          value={status}
          onChange={(event) => setStatus(event.target.value as (typeof STATUSES)[number])}
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {t(`flagStatus.${value}`)}
            </option>
          ))}
        </select>
      </label>
      {loading ? (
        <LoadingBlock label={t("queue.loading")} />
      ) : error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={error}
          retryLabel={t("queue.retry")}
          onRetry={() => void load()}
        />
      ) : (
        <FlagList flags={flags} onResolved={() => void load()} />
      )}
    </div>
  );
}
