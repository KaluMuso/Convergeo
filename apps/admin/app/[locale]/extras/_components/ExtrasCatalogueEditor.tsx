"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";
import { LoadingBlock } from "../../_components/StateBlocks";
import { ngweeToKwachaInput } from "../../home-feed/_components/feed-admin-api";

import {
  extraPayload,
  extrasApi,
  type AdminExtra,
  type ExtraDraft,
} from "./api";

const PRICING = ["fixed", "range", "pay_as_you_go"] as const;
const UNITS = ["one_off", "per_month", "per_item"] as const;

function toDraft(extra: AdminExtra): ExtraDraft {
  return {
    name: extra.name,
    description: extra.description,
    pricing: extra.pricing,
    price: ngweeToKwachaInput(extra.price_ngwee),
    priceMax: ngweeToKwachaInput(extra.price_max_ngwee),
    unit: extra.unit,
    active: extra.active,
  };
}

export function ExtrasCatalogueEditor() {
  const t = useTranslations("admin.extras");
  const [items, setItems] = useState<AdminExtra[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await extrasApi.request<AdminExtra[]>("/admin/extras"));
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(`queue.${failure.messageKey}`));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={t("queue.retry")}
        onRetry={() => void load()}
      />
    );
  }
  if (!items) return <LoadingBlock label={t("queue.loading")} />;
  return (
    <ul className="m-0 list-none space-y-3 p-0">
      {items.map((extra) => (
        <ExtraEditor
          key={extra.key}
          extra={extra}
          onSaved={() => void load()}
        />
      ))}
    </ul>
  );
}

function ExtraEditor({
  extra,
  onSaved,
}: {
  extra: AdminExtra;
  onSaved: () => void;
}) {
  const t = useTranslations("admin.extras");
  const [draft, setDraft] = useState<ExtraDraft>(() => toDraft(extra));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const set = <K extends keyof ExtraDraft>(key: K, value: ExtraDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const input =
    "min-h-11 rounded-md border border-border bg-surface px-2 text-sm text-text";

  async function save() {
    const payload = extraPayload(draft);
    if (!payload) {
      setMessage(t("errors.priceShape"));
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await extrasApi.request(`/admin/extras/${extra.key}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setMessage(t("catalogue.saved"));
      onSaved();
    } catch {
      setMessage(t("errors.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      className="space-y-2 rounded-md border border-border bg-surface p-3"
      data-testid={`extra-editor-${extra.key}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="m-0 font-medium text-text">{extra.key}</p>
        {extra.price_is_placeholder ? (
          <span className="rounded-pill bg-accent-tint px-2 py-0.5 text-xs font-semibold text-accent-deep">
            {t("catalogue.placeholder")}
          </span>
        ) : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("catalogue.name")}
          <input
            className={input}
            value={draft.name}
            maxLength={80}
            onChange={(e) => set("name", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("catalogue.pricing")}
          <select
            className={input}
            value={draft.pricing}
            onChange={(e) =>
              set("pricing", e.target.value as ExtraDraft["pricing"])
            }
          >
            {PRICING.map((value) => (
              <option key={value} value={value}>
                {t(`pricing.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("catalogue.price")}
          <input
            className={input}
            inputMode="decimal"
            value={draft.price}
            onChange={(e) => set("price", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("catalogue.priceMax")}
          <input
            className={input}
            inputMode="decimal"
            value={draft.priceMax}
            onChange={(e) => set("priceMax", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-2">
          {t("catalogue.unit")}
          <select
            className={input}
            value={draft.unit}
            onChange={(e) => set("unit", e.target.value as ExtraDraft["unit"])}
          >
            {UNITS.map((value) => (
              <option key={value} value={value}>
                {t(`unit.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={draft.active}
            onChange={(e) => set("active", e.target.checked)}
          />
          {t("catalogue.active")}
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs text-text-2">
        {t("catalogue.description")}
        <textarea
          className={`${input} py-2`}
          rows={2}
          maxLength={500}
          value={draft.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="min-h-11 rounded-md bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-60"
        >
          {t("catalogue.save")}
        </button>
        {extra.price_ngwee !== null ? (
          <span className="text-xs text-muted">
            {t("catalogue.current", { price: formatK(extra.price_ngwee) })}
          </span>
        ) : null}
        {message ? (
          <span role="status" className="text-xs text-text-2">
            {message}
          </span>
        ) : null}
      </div>
    </li>
  );
}
