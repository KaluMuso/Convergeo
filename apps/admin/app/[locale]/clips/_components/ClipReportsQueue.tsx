"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { adminClipsApi, type ReportItem } from "./api";

/**
 * M17-P07 — report triage.
 *
 * Two outcomes, both final and both audited: **dismiss** (the report was
 * unfounded, the clip is untouched) or **uphold** (the clip comes down and the
 * vendor takes a strike). There is deliberately no "snooze": a report that sits
 * in the queue unresolved is the failure mode the 24-hour target exists to
 * prevent, so the queue shows its age and flags anything past it.
 */
export function ClipReportsQueue() {
  const t = useTranslations("admin.clips.reports");
  const tRoot = useTranslations("admin.clips");
  const [items, setItems] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const result = await adminClipsApi.reports();
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

  const triage = useCallback(
    async (reportId: string, outcome: "dismiss" | "uphold") => {
      setBusyId(reportId);
      try {
        if (outcome === "dismiss") {
          await adminClipsApi.dismissReport(reportId, notes[reportId]);
        } else {
          await adminClipsApi.upholdReport(reportId, notes[reportId]);
        }
        await load();
      } catch {
        setError(t("error"));
      } finally {
        setBusyId(null);
      }
    },
    [load, notes, t],
  );

  if (loading) {
    return (
      <p className="text-sm text-muted" data-testid="admin-reports-loading">
        {tRoot("loading")}
      </p>
    );
  }

  if (error && items.length === 0) {
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
        data-testid="admin-reports-empty"
        className="rounded-lg border border-dashed border-border p-6 text-center"
      >
        <p className="font-medium text-text">{t("empty.title")}</p>
        <p className="mt-1 text-sm text-muted">{t("empty.body")}</p>
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-3" data-testid="admin-reports-queue">
      {items.map((item) => (
        <li
          key={item.report_id}
          data-testid="admin-report-row"
          data-sla-breached={item.sla_breached ? "true" : "false"}
          className="flex flex-col gap-2 rounded-2 border border-border bg-surface p-3"
        >
          <span
            className={`w-fit rounded-full px-2 py-1 text-xs ${
              item.sla_breached ? "bg-danger/15 text-danger" : "bg-bg-2 text-muted"
            }`}
          >
            {item.sla_breached ? t("slaBreached") : t("age", { hours: Math.round(item.age_hours) })}
          </span>

          {/* Reporter text is untrusted and is rendered as a text node. */}
          <p className="text-sm text-text" data-testid="admin-report-reason">
            {t("reason")}: {item.reason}
          </p>

          <label
            className="flex flex-col gap-1 text-sm text-text"
            htmlFor={`note-${item.report_id}`}
          >
            {t("noteLabel")}
            <input
              id={`note-${item.report_id}`}
              value={notes[item.report_id] ?? ""}
              onChange={(event) =>
                setNotes((current) => ({ ...current, [item.report_id]: event.target.value }))
              }
              className="min-h-11 rounded-2 border border-border bg-surface p-2"
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busyId === item.report_id}
              onClick={() => void triage(item.report_id, "dismiss")}
              data-testid="admin-report-dismiss"
              className="tap min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text disabled:opacity-50"
            >
              {t("dismiss")}
            </button>
            <button
              type="button"
              disabled={busyId === item.report_id}
              onClick={() => void triage(item.report_id, "uphold")}
              data-testid="admin-report-uphold"
              className="tap min-h-11 rounded-full border border-danger bg-surface px-4 py-2 text-sm text-danger disabled:opacity-50"
            >
              {t("uphold")}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
