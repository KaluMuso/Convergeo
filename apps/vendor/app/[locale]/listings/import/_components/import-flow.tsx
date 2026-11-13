"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { applyRawRows, downloadTemplateCsv, previewCsv } from "../_lib/import-client";
import { Button, Spinner } from "../_lib/ui";

import type {
  CanonicalSuggestion,
  ImportPreview,
  ImportSummary,
  RowPreview,
} from "../_lib/import-client";

const CANONICAL_REQUIRED = "listings.import.errors.canonicalRequired";

function rowReady(row: RowPreview, chosen?: CanonicalSuggestion): boolean {
  return (
    Object.keys(row.raw).length > 0 &&
    (row.ok ||
      (Boolean(chosen) &&
        row.errors.length > 0 &&
        row.errors.every((error) => error === CANONICAL_REQUIRED)))
  );
}

export function ImportFlow() {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const translateRowError = (error: string) =>
    error.startsWith("listings.import.errors.") && t.has(error)
      ? t(error)
      : t("listings.import.errors.unknownError");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [attached, setAttached] = useState<Record<number, CanonicalSuggestion>>({});
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleDownloadTemplate = useCallback(async () => {
    setDownloadingTemplate(true);
    setError(null);
    try {
      const csv = await downloadTemplateCsv(getToken);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "vergeo5-listings-template.csv";
        anchor.click();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch {
      setError(t("listings.import.errors.templateFailed"));
    } finally {
      setDownloadingTemplate(false);
    }
  }, [getToken, t]);

  const resetResults = useCallback(() => {
    setPreview(null);
    setSummary(null);
    setAttached({});
    setError(null);
  }, []);

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      setSelectedFile(event.target.files?.[0] ?? null);
      resetResults();
    },
    [resetResults],
  );

  const handlePreview = useCallback(async () => {
    if (!selectedFile || !session) {
      return;
    }
    setPreviewing(true);
    setError(null);
    setSummary(null);
    setAttached({});
    try {
      setPreview(await previewCsv(selectedFile, getToken));
    } catch {
      setError(t("listings.import.errors.previewFailed"));
    } finally {
      setPreviewing(false);
    }
  }, [getToken, selectedFile, session, t]);

  const handleApply = useCallback(async () => {
    if (!preview || !session) {
      return;
    }
    // Rebuild each parsed row, injecting the vendor's confirmed product_id.
    const rawRows = preview.rows
      .filter((row) => rowReady(row, attached[row.row]))
      .map((row) => {
        const chosen = attached[row.row]?.product_id ?? row.raw.product_id ?? "";
        return { ...row.raw, product_id: chosen };
      });
    if (rawRows.length === 0) {
      return;
    }
    setApplying(true);
    setError(null);
    try {
      setSummary(await applyRawRows(rawRows, getToken));
      setPreview(null);
    } catch {
      setError(t("listings.import.errors.uploadFailed"));
    } finally {
      setApplying(false);
    }
  }, [attached, getToken, preview, session, t]);

  const attachableCount = useMemo(
    () => (preview ? preview.rows.filter((row) => rowReady(row, attached[row.row])).length : 0),
    [attached, preview],
  );

  if (sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("listings.import.loading")} />
      </div>
    );
  }

  if (!session) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        {t("listings.import.signInRequired")}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="font-display text-2xl font-semibold text-[var(--color-text)]">
          {t("listings.import.title")}
        </h1>
        <p className="text-sm text-[var(--color-text-muted)]">{t("listings.import.intro")}</p>
      </header>

      <section className="flex flex-col gap-3 rounded-xl border border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold text-[var(--color-text)]">
          {t("listings.import.template.heading")}
        </h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          {t("listings.import.template.body")}
        </p>
        <p className="text-sm text-[var(--color-text-muted)]">
          {t("listings.import.template.unitsHelp")}
        </p>
        <p className="text-sm text-[var(--color-text-muted)]">
          {t("listings.import.template.stockNote")}
        </p>
        <Button
          type="button"
          variant="secondary"
          loadingLabel=""
          disabled={downloadingTemplate}
          onClick={() => void handleDownloadTemplate()}
        >
          {t("listings.import.template.download")}
        </Button>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold text-[var(--color-text)]">
          {t("listings.import.upload.heading")}
        </h2>
        <label className="flex min-h-11 cursor-pointer flex-col gap-2 text-sm">
          <span className="font-medium text-[var(--color-text)]">
            {t("listings.import.upload.fileLabel")}
          </span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            onChange={handleFileChange}
          />
        </label>
        {selectedFile ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {t("listings.import.upload.selected", { name: selectedFile.name })}
          </p>
        ) : null}
        <Button
          type="button"
          disabled={!selectedFile || previewing}
          loading={previewing}
          loadingLabel={t("listings.import.preview.previewing")}
          onClick={() => void handlePreview()}
        >
          {t("listings.import.preview.previewButton")}
        </Button>
        {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
      </section>

      {preview ? (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium text-[var(--color-text)]">
              {t("listings.import.preview.summary", {
                valid: attachableCount,
                total: preview.total,
              })}
            </p>
            <Button
              type="button"
              disabled={applying || attachableCount === 0}
              loading={applying}
              loadingLabel={t("listings.import.apply.applying")}
              onClick={() => void handleApply()}
            >
              {t("listings.import.apply.button")}
            </Button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="bg-[var(--color-surface-muted)]">
                <tr>
                  <th className="px-3 py-2 font-semibold">{t("listings.import.results.row")}</th>
                  <th className="px-3 py-2 font-semibold">{t("listings.import.results.status")}</th>
                  <th className="px-3 py-2 font-semibold">
                    {t("listings.import.preview.itemColumn")}
                  </th>
                  <th className="px-3 py-2 font-semibold">
                    {t("listings.import.preview.matchColumn")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => {
                  const chosen = attached[row.row];
                  const ready = rowReady(row, chosen);
                  const visibleErrors = chosen
                    ? row.errors.filter((error) => error !== CANONICAL_REQUIRED)
                    : row.errors;
                  return (
                    <tr key={row.row} className="border-t border-[var(--color-border)] align-top">
                      <td className="px-3 py-2 font-mono">{row.row}</td>
                      <td className="px-3 py-2">
                        {ready
                          ? t("listings.import.results.ok")
                          : t("listings.import.results.failed")}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-[var(--color-text)]">{row.title ?? "—"}</span>
                        {visibleErrors.length > 0 ? (
                          <span className="mt-1 block text-xs text-[var(--color-danger)]">
                            {visibleErrors.map(translateRowError).join("; ")}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        {row.product_id ? (
                          <span className="text-xs font-medium text-[var(--color-success)]">
                            {t("listings.import.preview.matched", {
                              name: row.matched_name ?? row.product_id,
                            })}
                          </span>
                        ) : chosen ? (
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-medium text-[var(--color-success)]">
                              {t("listings.import.preview.attached", {
                                name: chosen.name,
                              })}
                            </span>
                            <button
                              type="button"
                              className="text-xs underline"
                              onClick={() =>
                                setAttached((prev) => {
                                  const next = { ...prev };
                                  delete next[row.row];
                                  return next;
                                })
                              }
                            >
                              {t("listings.import.preview.detach")}
                            </button>
                          </span>
                        ) : row.suggestions.length > 0 ? (
                          <span className="flex flex-col gap-1">
                            <span className="text-xs text-[var(--color-text-muted)]">
                              {t("listings.import.preview.suggestionsLabel")}
                            </span>
                            {row.suggestions.map((suggestion) => (
                              <button
                                key={suggestion.product_id}
                                type="button"
                                className="min-h-9 rounded-md border border-[var(--color-border)] px-2 py-1 text-start text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-muted)]"
                                onClick={() =>
                                  setAttached((prev) => ({
                                    ...prev,
                                    [row.row]: suggestion,
                                  }))
                                }
                              >
                                {t("listings.import.preview.attachAction", {
                                  name: suggestion.name,
                                })}
                              </button>
                            ))}
                          </span>
                        ) : (
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {t("listings.import.preview.selectionRequired")}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {summary ? (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-4 text-sm">
            <p className="font-medium text-[var(--color-success)]">
              {t("listings.import.results.accepted", {
                count: summary.accepted,
              })}
            </p>
            <p className="font-medium text-[var(--color-danger)]">
              {t("listings.import.results.rejected", {
                count: summary.rejected,
              })}
            </p>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
            <table className="w-full min-w-[320px] text-left text-sm">
              <thead className="bg-[var(--color-surface-muted)]">
                <tr>
                  <th className="px-3 py-2 font-semibold">{t("listings.import.results.row")}</th>
                  <th className="px-3 py-2 font-semibold">{t("listings.import.results.status")}</th>
                  <th className="px-3 py-2 font-semibold">
                    {t("listings.import.results.details")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {summary.rows.map((row) => (
                  <tr key={row.row} className="border-t border-[var(--color-border)]">
                    <td className="px-3 py-2 font-mono">{row.row}</td>
                    <td className="px-3 py-2">
                      {row.ok
                        ? t("listings.import.results.ok")
                        : t("listings.import.results.failed")}
                    </td>
                    <td className="px-3 py-2 text-[var(--color-text-muted)]">
                      {row.ok
                        ? t(
                            row.stock_preserved
                              ? "listings.import.results.stockPreserved"
                              : "listings.import.results.imported",
                          )
                        : row.errors.map(translateRowError).join("; ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
