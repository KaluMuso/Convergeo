"use client";

import { formatK } from "@vergeo/i18n";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";

import {
  askAuditApi,
  askAuditQuery,
  storefrontUrl,
  type AskAuditAnswer,
  type AskAuditFilters,
  type AskAuditPage,
} from "./api";

const CUSTOMER_ORIGIN = process.env.NEXT_PUBLIC_VERGEO_CUSTOMER_URL ?? "http://localhost:3000";

const linkClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-text";
const inputClass = "min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text";

const SEVERITY_TONE: Record<string, string> = {
  critical: "bg-danger/10 text-danger",
  warning: "bg-warning/10 text-warning",
  info: "bg-surface text-text-2",
};

export function AskAuditBoard() {
  const t = useTranslations("admin.askAudit");
  const locale = useLocale();
  const [filters, setFilters] = useState<AskAuditFilters>({ flaggedOnly: true, severity: "" });
  const [items, setItems] = useState<AskAuditAnswer[] | null>(null);
  const [next, setNext] = useState<{ before: string; beforeId: string | null } | null>(null);
  const [error, setError] = useState<"error" | "permissionDenied" | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (cursor?: { before: string; beforeId: string | null }) => {
      setError(null);
      setBusy(true);
      try {
        const page = await askAuditApi.request<AskAuditPage>(
          `/admin/ask-audit?${askAuditQuery(filters, cursor)}`,
        );
        setItems((current) => (cursor && current ? [...current, ...page.items] : page.items));
        setNext(
          page.next_before ? { before: page.next_before, beforeId: page.next_before_id } : null,
        );
      } catch (err) {
        const failure = resolveQueueLoadFailure(err);
        setPermissionDenied(failure.permissionDenied);
        setError(failure.messageKey);
      } finally {
        setBusy(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    setItems(null);
    void load();
  }, [load]);

  return (
    <div className="space-y-3">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => event.preventDefault()}
        aria-label={t("filters.label")}
      >
        <label className="flex min-h-11 items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={filters.flaggedOnly}
            onChange={(event) => setFilters({ ...filters, flaggedOnly: event.target.checked })}
            data-testid="ask-audit-flagged-only"
          />
          {t("filters.flaggedOnly")}
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("filters.severity")}
          <select
            className={inputClass}
            value={filters.severity}
            onChange={(event) =>
              setFilters({
                ...filters,
                severity: event.target.value as AskAuditFilters["severity"],
              })
            }
          >
            <option value="">{t("filters.severityAll")}</option>
            <option value="critical">{t("severity.critical")}</option>
            <option value="warning">{t("severity.warning")}</option>
          </select>
        </label>
      </form>

      {error ? (
        <AdminLoadFailure
          permissionDenied={permissionDenied}
          message={t(error)}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : items === null ? (
        <LoadingBlock label={t("loading")} />
      ) : items.length === 0 ? (
        <EmptyBlock title={filters.flaggedOnly ? t("emptyFlagged") : t("empty")} />
      ) : (
        <>
          <ul className="m-0 list-none space-y-3 p-0">
            {items.map((answer) => (
              <AnswerCard key={answer.id} answer={answer} locale={locale} />
            ))}
          </ul>
          {next ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void load(next)}
              className={`${linkClass} disabled:opacity-60`}
            >
              {t("loadMore")}
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}

function AnswerCard({ answer, locale }: { answer: AskAuditAnswer; locale: string }) {
  const t = useTranslations("admin.askAudit");
  const when = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Lusaka",
  }).format(new Date(answer.created_at));
  const link = (path: string | null) => storefrontUrl(CUSTOMER_ORIGIN, locale, path);

  return (
    <li
      className="space-y-3 rounded-md border border-border bg-surface p-3"
      data-testid={`ask-audit-${answer.id}`}
      data-status={answer.audit_status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-2">
        <span
          className={`rounded-full px-2 py-1 font-medium ${
            SEVERITY_TONE[answer.audit_severity ?? "info"] ?? SEVERITY_TONE.info
          }`}
        >
          {t(`status.${answer.audit_status}`)}
          {answer.audit_severity ? ` · ${t(`severity.${answer.audit_severity}`)}` : ""}
        </span>
        <span>
          {when} · {t(`asker.${answer.asker}`)} · {answer.source}
          {answer.model ? ` · ${answer.model}` : ""}
        </span>
      </div>

      <div className="space-y-1">
        <p className="m-0 text-xs font-medium text-text-2">{t("question")}</p>
        <p className="m-0 text-sm text-text">{answer.query}</p>
        <p className="m-0 text-xs font-medium text-text-2">{t("answer")}</p>
        <p className="m-0 whitespace-pre-line text-sm text-text">{answer.answer_text}</p>
      </div>

      {answer.findings.length > 0 ? (
        <div className="space-y-2" data-testid="ask-audit-findings">
          <p className="m-0 text-xs font-semibold text-text">{t("findings")}</p>
          <ul className="m-0 list-none space-y-2 p-0">
            {answer.findings.map((finding) => {
              const itemUrl = link(finding.entity_href);
              const vendorUrl = link(finding.vendor_href);
              return (
                <li
                  key={finding.id}
                  className="space-y-2 rounded-md border border-border p-2"
                  data-testid="ask-audit-finding"
                  data-rule={finding.rule}
                >
                  <p className="m-0 text-sm text-text">
                    <span
                      className={`me-2 rounded-full px-2 py-0.5 text-xs font-medium ${
                        SEVERITY_TONE[finding.severity] ?? SEVERITY_TONE.info
                      }`}
                    >
                      {t(`severity.${finding.severity}`)}
                    </span>
                    <span className="font-medium">{t(`rules.${finding.rule}`)}</span>
                  </p>
                  <p className="m-0 text-sm text-text-2">{finding.reason}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {itemUrl ? (
                      <a
                        className={linkClass}
                        href={itemUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="ask-audit-item-link"
                      >
                        {t("viewItem")}
                      </a>
                    ) : null}
                    {vendorUrl ? (
                      <a
                        className={linkClass}
                        href={vendorUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="ask-audit-vendor-link"
                      >
                        {t("viewVendor", { vendor: finding.vendor_name ?? "" })}
                      </a>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {answer.citations.length > 0 ? (
        <div className="space-y-1">
          <p className="m-0 text-xs font-semibold text-text">{t("citedItems")}</p>
          <ul className="m-0 list-none space-y-1 p-0 text-sm text-text-2">
            {answer.citations.map((cited) => {
              const itemUrl = link(cited.href);
              const vendorUrl = link(cited.vendor_href);
              return (
                <li key={`${cited.kind}:${cited.id}`} className="flex flex-wrap gap-x-2">
                  {itemUrl ? (
                    <a
                      href={itemUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {cited.title}
                    </a>
                  ) : (
                    <span>{cited.title}</span>
                  )}
                  {cited.price_ngwee !== null ? <span>{formatK(cited.price_ngwee)}</span> : null}
                  {vendorUrl ? (
                    <a
                      href={vendorUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {cited.vendor_name ?? t("vendor")}
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </li>
  );
}
