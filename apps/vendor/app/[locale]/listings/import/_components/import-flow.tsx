"use client";

import { useSession } from "@vergeo/auth/use-session";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { importCsv } from "../_lib/import-client";
import { Button, Spinner } from "../_lib/ui";

import type { ImportSummary } from "../_lib/import-client";

const TEMPLATE_CSV = `sku,title,price_ngwee,stock_mode,stock_qty,condition,wholesale,moq,status
TOM-001,Fresh tomatoes per kg,2500,tracked,50,new,false,1,active
RICE-10KG,White rice 10kg bag,18500,tracked,20,new,false,1,active`;

export function ImportFlow() {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);

  const handleDownloadTemplate = useCallback(() => {
    const blob = new Blob([TEMPLATE_CSV], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "vergeo5-listings-template.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }, []);

  const handleFileChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setSummary(null);
    setError(null);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!selectedFile || !session) {
      return;
    }
    setUploading(true);
    setError(null);
    setSummary(null);
    try {
      const result = await importCsv(selectedFile, getToken);
      setSummary(result);
    } catch {
      setError(t("listings.import.errors.uploadFailed"));
    } finally {
      setUploading(false);
    }
  }, [getToken, selectedFile, session, t]);

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
        <Button type="button" variant="secondary" loadingLabel="" onClick={handleDownloadTemplate}>
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
          disabled={!selectedFile || uploading}
          loading={uploading}
          loadingLabel={t("listings.import.upload.uploading")}
          onClick={() => void handleUpload()}
        >
          {t("listings.import.upload.submit")}
        </Button>
        {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
      </section>

      {summary ? (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-4 text-sm">
            <p className="font-medium text-[var(--color-success)]">
              {t("listings.import.results.accepted", { count: summary.accepted })}
            </p>
            <p className="font-medium text-[var(--color-danger)]">
              {t("listings.import.results.rejected", { count: summary.rejected })}
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
                      {row.ok ? t("listings.import.results.imported") : row.errors.join("; ")}
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
