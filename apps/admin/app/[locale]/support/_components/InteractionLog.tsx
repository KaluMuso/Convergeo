"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type InteractionLogEntry, supportApi } from "./api";

type InteractionLogProps = {
  customerId: string;
  refreshKey: number;
  locale: string;
};

export function InteractionLog({ customerId, refreshKey, locale }: InteractionLogProps) {
  const t = useTranslations("admin.support.log");
  const tTemplates = useTranslations("admin.support.templates");
  const [entries, setEntries] = useState<InteractionLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await supportApi.request<InteractionLogEntry[]>(
        `/admin/support/log?customer_id=${encodeURIComponent(customerId)}`,
      );
      setEntries(data);
    } catch {
      setError(t("error"));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [customerId, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section className="space-y-4 rounded-lg border border-[#E8DFD0] bg-white p-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-[#2A2118]">{t("title")}</h2>
        <p className="text-sm text-[#6B5E4C]">{t("subtitle")}</p>
      </header>

      {loading ? <p className="text-sm text-[#6B5E4C]">{t("loading")}</p> : null}

      {error ? (
        <div className="space-y-2">
          <p className="text-sm text-[#9B2C2C]">{error}</p>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
            onClick={() => void load()}
          >
            {t("retry")}
          </button>
        </div>
      ) : null}

      {!loading && !error && entries.length === 0 ? (
        <p className="text-sm text-[#6B5E4C]">{t("empty")}</p>
      ) : null}

      {!loading && entries.length > 0 ? (
        <ul className="space-y-3">
          {entries.map((entry) => (
            <li
              key={`${entry.source}-${entry.id}`}
              className="rounded-md border border-[#F0E9DE] p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#6B5E4C]">
                <span>{new Date(entry.created_at).toLocaleString(locale)}</span>
                <span>
                  {entry.kind === "canned" ? t("kindCanned") : t("kindFreeText")}
                  {entry.channel ? ` · ${entry.channel}` : ""}
                </span>
              </div>
              {entry.template_key ? (
                <p className="mt-1 text-sm font-medium text-[#2A2118]">
                  {tTemplates(`${entry.template_key}.label`)}
                </p>
              ) : null}
              {entry.message_preview ? (
                <p className="mt-1 text-sm text-[#2A2118]">{entry.message_preview}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
