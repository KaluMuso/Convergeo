"use client";

import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  AUDIENCES,
  feedAdminApi,
  fromLocalDatetime,
  moveItem,
  ngweeToKwachaInput,
  parseKwachaToNgwee,
  RULE_SORTS,
  SECTION_LAYOUTS,
  SECTION_TYPES,
  splitList,
  toLocalDatetime,
  type FeedSectionRow,
  type PreviewPage,
  type SectionConfig,
  type SectionType,
} from "./feed-admin-api";

type Draft = {
  id: string | null;
  key: string;
  section_type: SectionType;
  layout: string;
  title_key: string;
  title_en: string;
  title_fr: string;
  limit: string;
  category_path: string;
  listing_ids: string;
  rule_paths: string;
  rule_price_max: string;
  rule_sort: string;
  rule_keywords: string;
  rule_new_days: string;
  within_days: string;
  view_all_href: string;
  starts_at: string;
  ends_at: string;
  audience: string;
  enabled: boolean;
};

const EMPTY_DRAFT: Draft = {
  id: null,
  key: "",
  section_type: "rule",
  layout: "rail",
  title_key: "",
  title_en: "",
  title_fr: "",
  limit: "12",
  category_path: "",
  listing_ids: "",
  rule_paths: "",
  rule_price_max: "",
  rule_sort: "relevance",
  rule_keywords: "",
  rule_new_days: "",
  within_days: "",
  view_all_href: "",
  starts_at: "",
  ends_at: "",
  audience: "all",
  enabled: true,
};

function draftFromRow(row: FeedSectionRow): Draft {
  const rule = row.config.rule ?? {};
  return {
    id: row.id,
    key: row.key,
    section_type: row.section_type,
    layout: row.layout,
    title_key: row.title_key ?? "",
    title_en: row.title_i18n.en ?? "",
    title_fr: row.title_i18n.fr ?? "",
    limit: String(row.config.limit ?? 12),
    category_path: row.config.category_path ?? "",
    listing_ids: (row.config.listing_ids ?? []).join("\n"),
    rule_paths: (rule.category_paths ?? []).join(", "),
    rule_price_max: ngweeToKwachaInput(rule.price_max_ngwee ?? null),
    rule_sort: rule.sort ?? "relevance",
    rule_keywords: (rule.keywords ?? []).join(", "),
    rule_new_days: rule.new_within_days ? String(rule.new_within_days) : "",
    within_days: row.config.within_days ? String(row.config.within_days) : "",
    view_all_href: row.config.view_all_href ?? "",
    starts_at: toLocalDatetime(row.starts_at),
    ends_at: toLocalDatetime(row.ends_at),
    audience: row.audience,
    enabled: row.enabled,
  };
}

/** Build the API body; returns an error key when a money field is invalid. */
export function draftToBody(draft: Draft): { body: Record<string, unknown> } | { error: string } {
  const config: SectionConfig = { limit: Number.parseInt(draft.limit, 10) || 12 };
  if (draft.view_all_href.trim()) config.view_all_href = draft.view_all_href.trim();
  if (draft.section_type === "category") config.category_path = draft.category_path.trim();
  if (draft.section_type === "collection") config.listing_ids = splitList(draft.listing_ids);
  if (draft.section_type === "events" && draft.within_days)
    config.within_days = Number.parseInt(draft.within_days, 10);
  if (draft.section_type === "rule") {
    let priceMax: number | null = null;
    if (draft.rule_price_max.trim()) {
      priceMax = parseKwachaToNgwee(draft.rule_price_max);
      if (priceMax === null) return { error: "invalidPrice" };
    }
    config.rule = {
      category_paths: splitList(draft.rule_paths),
      keywords: splitList(draft.rule_keywords),
      sort: draft.rule_sort as (typeof RULE_SORTS)[number],
      ...(priceMax !== null ? { price_max_ngwee: priceMax } : {}),
      ...(draft.rule_new_days ? { new_within_days: Number.parseInt(draft.rule_new_days, 10) } : {}),
    };
  }
  const titles: Record<string, string> = {};
  if (draft.title_en.trim()) titles.en = draft.title_en.trim();
  if (draft.title_fr.trim()) titles.fr = draft.title_fr.trim();
  const body: Record<string, unknown> = {
    layout: draft.section_type === "ad_slot" ? "ad" : draft.layout,
    title_key: draft.title_key.trim() || null,
    title_i18n: titles,
    config,
    enabled: draft.enabled,
    audience: draft.audience,
    starts_at: fromLocalDatetime(draft.starts_at),
    ends_at: fromLocalDatetime(draft.ends_at),
  };
  if (!draft.id) {
    body.key = draft.key.trim();
    body.section_type = draft.section_type;
  } else if (!draft.starts_at && !draft.ends_at) {
    body.clear_schedule = true;
  }
  return { body };
}

const inputClass = "min-h-11 w-full rounded-md border border-border bg-bg px-3 text-sm";
const buttonClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium";

export function HomeFeedBoard() {
  const t = useTranslations("admin.homeFeed");
  const [rows, setRows] = useState<FeedSectionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<PreviewPage | null>(null);
  const [dirtyOrder, setDirtyOrder] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await feedAdminApi.request<FeedSectionRow[]>("/admin/home-feed/sections"));
      setDirtyOrder(false);
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!draft) return;
    const built = draftToBody(draft);
    if ("error" in built) {
      notify.error(t(`errors.${built.error}`));
      return;
    }
    try {
      await feedAdminApi.request(
        draft.id ? `/admin/home-feed/sections/${draft.id}` : "/admin/home-feed/sections",
        { method: draft.id ? "PATCH" : "POST", body: JSON.stringify(built.body) },
      );
      notify.success(t("saved"));
      setDraft(null);
      await load();
    } catch {
      notify.error(t("saveError"));
    }
  };

  const toggle = async (row: FeedSectionRow) => {
    try {
      await feedAdminApi.request(`/admin/home-feed/sections/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      await load();
    } catch {
      notify.error(t("saveError"));
    }
  };

  const remove = async (row: FeedSectionRow) => {
    if (!window.confirm(t("confirmDelete"))) return;
    try {
      await feedAdminApi.request(`/admin/home-feed/sections/${row.id}`, { method: "DELETE" });
      await load();
    } catch {
      notify.error(t("saveError"));
    }
  };

  const saveOrder = async () => {
    try {
      const fresh = await feedAdminApi.request<FeedSectionRow[]>(
        "/admin/home-feed/sections/reorder",
        { method: "POST", body: JSON.stringify({ ordered_ids: rows.map((row) => row.id) }) },
      );
      setRows(fresh);
      setDirtyOrder(false);
      notify.success(t("orderSaved"));
    } catch {
      notify.error(t("saveError"));
    }
  };

  const loadPreview = async () => {
    try {
      setPreview(await feedAdminApi.request<PreviewPage>("/admin/home-feed/preview"));
    } catch {
      notify.error(t("previewError"));
    }
  };

  if (loading) return <p className="text-sm text-muted">{t("loading")}</p>;
  if (error)
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error}</p>
        <button type="button" className={buttonClass} onClick={() => void load()}>
          {t("retry")}
        </button>
      </div>
    );

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm text-white"
          onClick={() => setDraft({ ...EMPTY_DRAFT })}
        >
          {t("create")}
        </button>
        <button type="button" className={buttonClass} onClick={() => void loadPreview()}>
          {t("preview")}
        </button>
        {dirtyOrder ? (
          <button type="button" className={buttonClass} onClick={() => void saveOrder()}>
            {t("saveOrder")}
          </button>
        ) : null}
      </div>
      <p className="text-xs text-muted">{t("hint")}</p>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-2 py-3 font-medium">{t("columns.order")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.key")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.type")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.schedule")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.status")}</th>
              <th className="px-2 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.id} className="border-b border-border align-top">
                <td className="px-2 py-3">
                  <div className="flex gap-1">
                    <button
                      type="button"
                      className={buttonClass}
                      aria-label={t("moveUp", { key: row.key })}
                      disabled={index === 0}
                      onClick={() => {
                        setRows((current) => moveItem(current, index, -1));
                        setDirtyOrder(true);
                      }}
                    >
                      {t("arrowUp")}
                    </button>
                    <button
                      type="button"
                      className={buttonClass}
                      aria-label={t("moveDown", { key: row.key })}
                      disabled={index === rows.length - 1}
                      onClick={() => {
                        setRows((current) => moveItem(current, index, 1));
                        setDirtyOrder(true);
                      }}
                    >
                      {t("arrowDown")}
                    </button>
                  </div>
                </td>
                <td className="px-2 py-3 font-medium text-text">
                  {row.title_i18n.en ?? row.key}
                  <div className="text-xs text-muted">{row.key}</div>
                </td>
                <td className="px-2 py-3 text-muted">
                  {t(`types.${row.section_type}`)} · {t(`layouts.${row.layout}`)}
                </td>
                <td className="px-2 py-3 text-muted">
                  {row.starts_at || row.ends_at
                    ? t("scheduleRange", {
                        from: row.starts_at ? new Date(row.starts_at).toLocaleString() : "—",
                        to: row.ends_at ? new Date(row.ends_at).toLocaleString() : "—",
                      })
                    : t("scheduleOpen")}
                </td>
                <td className="px-2 py-3">
                  <span
                    className={[
                      "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                      row.live ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                    ].join(" ")}
                  >
                    {row.live ? t("live") : row.enabled ? t("scheduled") : t("disabled")}
                  </span>
                </td>
                <td className="px-2 py-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={buttonClass}
                      onClick={() => setDraft(draftFromRow(row))}
                    >
                      {t("edit")}
                    </button>
                    <button type="button" className={buttonClass} onClick={() => void toggle(row)}>
                      {row.enabled ? t("disable") : t("enable")}
                    </button>
                    <button type="button" className={buttonClass} onClick={() => void remove(row)}>
                      {t("delete")}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {draft ? (
        <form
          className="grid gap-3 rounded-md border border-border bg-bg p-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <h2 className="font-serif text-lg text-text md:col-span-2">
            {draft.id ? t("editTitle") : t("createTitle")}
          </h2>
          <label className="space-y-1 text-sm">
            <span>{t("fields.key")}</span>
            <input
              className={inputClass}
              value={draft.key}
              disabled={Boolean(draft.id)}
              required
              pattern="[a-z][a-z0-9_]{2,63}"
              onChange={(event) => set("key", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.type")}</span>
            <select
              className={inputClass}
              value={draft.section_type}
              disabled={Boolean(draft.id)}
              onChange={(event) => set("section_type", event.target.value as SectionType)}
            >
              {SECTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(`types.${type}`)}
                </option>
              ))}
            </select>
          </label>
          {draft.section_type !== "ad_slot" ? (
            <>
              <label className="space-y-1 text-sm">
                <span>{t("fields.layout")}</span>
                <select
                  className={inputClass}
                  value={draft.layout}
                  onChange={(event) => set("layout", event.target.value)}
                >
                  {SECTION_LAYOUTS.filter((layout) => layout !== "ad").map((layout) => (
                    <option key={layout} value={layout}>
                      {t(`layouts.${layout}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.titleKey")}</span>
                <input
                  className={inputClass}
                  value={draft.title_key}
                  onChange={(event) => set("title_key", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.titleEn")}</span>
                <input
                  className={inputClass}
                  value={draft.title_en}
                  maxLength={80}
                  onChange={(event) => set("title_en", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.titleFr")}</span>
                <input
                  className={inputClass}
                  value={draft.title_fr}
                  maxLength={80}
                  onChange={(event) => set("title_fr", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.limit")}</span>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  max={24}
                  value={draft.limit}
                  onChange={(event) => set("limit", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.viewAll")}</span>
                <input
                  className={inputClass}
                  value={draft.view_all_href}
                  placeholder={t("placeholders.path")}
                  onChange={(event) => set("view_all_href", event.target.value)}
                />
              </label>
            </>
          ) : null}
          {draft.section_type === "category" ? (
            <label className="space-y-1 text-sm md:col-span-2">
              <span>{t("fields.categoryPath")}</span>
              <input
                className={inputClass}
                value={draft.category_path}
                required
                onChange={(event) => set("category_path", event.target.value)}
              />
            </label>
          ) : null}
          {draft.section_type === "collection" ? (
            <label className="space-y-1 text-sm md:col-span-2">
              <span>{t("fields.listingIds")}</span>
              <textarea
                className={`${inputClass} min-h-24 py-2`}
                value={draft.listing_ids}
                onChange={(event) => set("listing_ids", event.target.value)}
              />
            </label>
          ) : null}
          {draft.section_type === "events" ? (
            <label className="space-y-1 text-sm">
              <span>{t("fields.withinDays")}</span>
              <input
                className={inputClass}
                type="number"
                min={1}
                max={60}
                value={draft.within_days}
                onChange={(event) => set("within_days", event.target.value)}
              />
            </label>
          ) : null}
          {draft.section_type === "rule" ? (
            <>
              <label className="space-y-1 text-sm">
                <span>{t("fields.rulePaths")}</span>
                <input
                  className={inputClass}
                  value={draft.rule_paths}
                  placeholder={t("placeholders.paths")}
                  onChange={(event) => set("rule_paths", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.rulePriceMax")}</span>
                <input
                  className={inputClass}
                  inputMode="decimal"
                  value={draft.rule_price_max}
                  onChange={(event) => set("rule_price_max", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.ruleSort")}</span>
                <select
                  className={inputClass}
                  value={draft.rule_sort}
                  onChange={(event) => set("rule_sort", event.target.value)}
                >
                  {RULE_SORTS.map((sort) => (
                    <option key={sort} value={sort}>
                      {t(`sorts.${sort}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.ruleKeywords")}</span>
                <input
                  className={inputClass}
                  value={draft.rule_keywords}
                  onChange={(event) => set("rule_keywords", event.target.value)}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span>{t("fields.ruleNewDays")}</span>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  max={365}
                  value={draft.rule_new_days}
                  onChange={(event) => set("rule_new_days", event.target.value)}
                />
              </label>
            </>
          ) : null}
          <label className="space-y-1 text-sm">
            <span>{t("fields.startsAt")}</span>
            <input
              className={inputClass}
              type="datetime-local"
              value={draft.starts_at}
              onChange={(event) => set("starts_at", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.endsAt")}</span>
            <input
              className={inputClass}
              type="datetime-local"
              value={draft.ends_at}
              onChange={(event) => set("ends_at", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.audience")}</span>
            <select
              className={inputClass}
              value={draft.audience}
              onChange={(event) => set("audience", event.target.value)}
            >
              {AUDIENCES.map((audience) => (
                <option key={audience} value={audience}>
                  {t(`audiences.${audience}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => set("enabled", event.target.checked)}
            />
            <span>{t("fields.enabled")}</span>
          </label>
          <div className="flex gap-2 md:col-span-2">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm text-white"
            >
              {t("save")}
            </button>
            <button type="button" className={buttonClass} onClick={() => setDraft(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}

      {preview ? (
        <section className="space-y-2 rounded-md border border-border p-4" aria-live="polite">
          <h2 className="font-serif text-lg text-text">{t("previewTitle")}</h2>
          {preview.carousel.length > 0 ? (
            <p className="text-sm text-muted">
              {t("previewCarousel", { count: preview.carousel.length })}
            </p>
          ) : null}
          {preview.sections.length === 0 ? (
            <p className="text-sm text-muted">{t("previewEmpty")}</p>
          ) : (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {preview.sections.map((section) => (
                <li key={section.id}>
                  {section.key} —{" "}
                  {section.ad
                    ? t("previewAd", { advertiser: section.ad.advertiser_name })
                    : t("previewCount", {
                        count:
                          section.listings.length +
                          section.services.length +
                          section.events.length +
                          section.vendors.length,
                      })}
                </li>
              ))}
            </ol>
          )}
        </section>
      ) : null}
    </div>
  );
}
