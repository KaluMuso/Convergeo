"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type ContextCard, supportApi } from "./api";
import { ContextCardView } from "./ContextCard";
import { InteractionLog } from "./InteractionLog";
import { ReplyComposer } from "./ReplyComposer";

type SupportInboxProps = {
  locale: string;
};

export function SupportInbox({ locale }: SupportInboxProps) {
  const t = useTranslations("admin.support");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<ContextCard[]>([]);
  const [selected, setSelected] = useState<ContextCard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [logRefreshKey, setLogRefreshKey] = useState(0);

  const runLookup = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setError(t("lookup.needQuery"));
      return;
    }
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const data = await supportApi.request<{ matches: ContextCard[] }>(
        `/admin/support/lookup?q=${encodeURIComponent(trimmed)}`,
      );
      setMatches(data.matches);
      setSelected(data.matches[0] ?? null);
    } catch {
      setError(t("lookup.error"));
      setMatches([]);
      setSelected(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSent = () => {
    setLogRefreshKey((value) => value + 1);
  };

  return (
    <div className="space-y-6">
      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          void runLookup();
        }}
      >
        <label className="min-w-0 flex-1 space-y-1 text-sm">
          <span className="text-muted">{t("lookup.label")}</span>
          <input
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("lookup.placeholder")}
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-white sm:w-auto"
            disabled={loading}
          >
            {loading ? t("lookup.searching") : t("lookup.submit")}
          </button>
        </div>
      </form>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {searched && !loading && matches.length === 0 ? (
        <p className="text-sm text-muted">{t("lookup.empty")}</p>
      ) : null}

      {matches.length > 1 ? (
        <div className="space-y-2">
          <p className="text-sm font-medium text-text">{t("lookup.multiple")}</p>
          <div className="flex flex-wrap gap-2">
            {matches.map((match) => (
              <button
                key={match.customer.id}
                type="button"
                className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
                  selected?.customer.id === match.customer.id
                    ? "border-primary bg-primary-tint text-primary"
                    : "border-border text-text"
                }`}
                onClick={() => setSelected(match)}
              >
                {match.customer.display_name ?? match.customer.phone ?? match.customer.id}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {selected ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <ContextCardView card={selected} locale={locale} />
            <ReplyComposer
              customerId={selected.customer.id}
              orderId={selected.orders[0]?.id ?? null}
              onSent={handleSent}
            />
          </div>
          <InteractionLog
            customerId={selected.customer.id}
            refreshKey={logRefreshKey}
            locale={locale}
          />
        </div>
      ) : null}
    </div>
  );
}
