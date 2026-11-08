"use client";

import { formatK } from "@vergeo/i18n";
import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  feedAdminApi,
  fromLocalDatetime,
  parseKwachaToNgwee,
  toLocalDatetime,
} from "../../home-feed/_components/feed-admin-api";

type PlacementStatus = "draft" | "scheduled" | "active" | "paused" | "ended";

export type Placement = {
  id: string;
  advertiser_kind: "vendor" | "business" | "external";
  advertiser_vendor_id: string | null;
  advertiser_name: string;
  placement_type: "feed_slot" | "carousel_slide";
  image_public_id: string;
  headline: string;
  body: string | null;
  cta_label: string | null;
  cta_href: string;
  starts_at: string;
  ends_at: string;
  priority: number;
  paid_amount_ngwee: number;
  payment_reference: string | null;
  status: PlacementStatus;
  enabled: boolean;
  effective_state: string;
  stats: { impressions: number; clicks: number; ctr_bp: number };
};

/** Mirrors public.transition_ad_placement edges (server is authoritative). */
export const NEXT_STATUSES: Record<PlacementStatus, PlacementStatus[]> = {
  draft: ["scheduled"],
  scheduled: ["active", "paused", "draft", "ended"],
  active: ["paused", "ended"],
  paused: ["active", "scheduled", "ended"],
  ended: [],
};

/** CTR from integer basis points → "1.23%" without floating money-style math. */
export function formatCtr(basisPoints: number): string {
  const whole = Math.trunc(basisPoints / 100);
  const fraction = String(basisPoints % 100).padStart(2, "0");
  return `${whole}.${fraction}%`;
}

type Form = {
  advertiser_kind: Placement["advertiser_kind"];
  advertiser_vendor_id: string;
  advertiser_name: string;
  placement_type: Placement["placement_type"];
  image_public_id: string;
  headline: string;
  body: string;
  cta_label: string;
  cta_href: string;
  starts_at: string;
  ends_at: string;
  priority: string;
  paid_amount: string;
  payment_reference: string;
};

const EMPTY_FORM: Form = {
  advertiser_kind: "external",
  advertiser_vendor_id: "",
  advertiser_name: "",
  placement_type: "feed_slot",
  image_public_id: "",
  headline: "",
  body: "",
  cta_label: "",
  cta_href: "",
  starts_at: "",
  ends_at: "",
  priority: "0",
  paid_amount: "0",
  payment_reference: "",
};

const inputClass = "min-h-11 w-full rounded-md border border-border bg-bg px-3 text-sm";
const buttonClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium";

export function AdvertisingBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.advertising");
  const [rows, setRows] = useState<Placement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await feedAdminApi.request<Placement[]>("/admin/ads/placements"));
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (!form) return;
    const paid = parseKwachaToNgwee(form.paid_amount || "0");
    const startsAt = fromLocalDatetime(form.starts_at);
    const endsAt = fromLocalDatetime(form.ends_at);
    if (paid === null) {
      notify.error(t("errors.invalidAmount"));
      return;
    }
    if (!startsAt || !endsAt || endsAt <= startsAt) {
      notify.error(t("errors.invalidWindow"));
      return;
    }
    try {
      await feedAdminApi.request("/admin/ads/placements", {
        method: "POST",
        body: JSON.stringify({
          advertiser_kind: form.advertiser_kind,
          advertiser_vendor_id: form.advertiser_vendor_id.trim() || null,
          advertiser_name: form.advertiser_name.trim(),
          placement_type: form.placement_type,
          image_public_id: form.image_public_id.trim(),
          headline: form.headline.trim(),
          body: form.body.trim() || null,
          cta_label: form.cta_label.trim() || null,
          cta_href: form.cta_href.trim(),
          starts_at: startsAt,
          ends_at: endsAt,
          priority: Number.parseInt(form.priority, 10) || 0,
          paid_amount_ngwee: paid,
          payment_reference: form.payment_reference.trim() || null,
        }),
      });
      notify.success(t("created"));
      setForm(null);
      await load();
    } catch {
      notify.error(t("saveError"));
    }
  };

  const transition = async (row: Placement, toStatus: PlacementStatus) => {
    if (toStatus === "ended" && !window.confirm(t("confirmEnd"))) return;
    try {
      await feedAdminApi.request(`/admin/ads/placements/${row.id}/transition`, {
        method: "POST",
        body: JSON.stringify({ to_status: toStatus }),
      });
      await load();
    } catch {
      notify.error(t("transitionError"));
    }
  };

  const toggle = async (row: Placement) => {
    try {
      await feedAdminApi.request(`/admin/ads/placements/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      await load();
    } catch {
      notify.error(t("saveError"));
    }
  };

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleString(locale, { timeZone: "Africa/Lusaka" });
  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm((current) => (current ? { ...current, [key]: value } : current));

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm text-white"
          onClick={() => setForm({ ...EMPTY_FORM })}
        >
          {t("create")}
        </button>
        <p className="text-xs text-muted">{t("hint")}</p>
      </div>

      {rows.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <th className="px-2 py-3 font-medium">{t("columns.creative")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.window")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.paid")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.status")}</th>
              <th className="px-2 py-3 font-medium">{t("columns.performance")}</th>
              <th className="px-2 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border align-top">
                <td className="px-2 py-3">
                  <div className="font-medium text-text">{row.headline}</div>
                  <div className="text-xs text-muted">
                    {row.advertiser_name} · {t(`kinds.${row.advertiser_kind}`)} ·{" "}
                    {t(`types.${row.placement_type}`)}
                  </div>
                </td>
                <td className="px-2 py-3 text-muted">
                  {t("windowRange", { from: fmtDate(row.starts_at), to: fmtDate(row.ends_at) })}
                </td>
                <td className="px-2 py-3 text-muted">
                  {formatK(row.paid_amount_ngwee)}
                  {row.payment_reference ? (
                    <div className="text-xs">{row.payment_reference}</div>
                  ) : null}
                </td>
                <td className="px-2 py-3">
                  <span className="inline-flex rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-text">
                    {t(`statuses.${row.status}`)}
                  </span>
                  <div className="mt-1 text-xs text-muted">
                    {t(`effective.${row.effective_state}`)}
                  </div>
                </td>
                <td className="px-2 py-3 text-muted">
                  {t("performance", {
                    impressions: row.stats.impressions,
                    clicks: row.stats.clicks,
                    ctr: formatCtr(row.stats.ctr_bp),
                  })}
                </td>
                <td className="px-2 py-3">
                  <div className="flex flex-wrap gap-2">
                    {NEXT_STATUSES[row.status].map((next) => (
                      <button
                        key={next}
                        type="button"
                        className={buttonClass}
                        onClick={() => void transition(row, next)}
                      >
                        {t(`actions.${next}`)}
                      </button>
                    ))}
                    {row.status !== "ended" ? (
                      <button
                        type="button"
                        className={buttonClass}
                        onClick={() => void toggle(row)}
                      >
                        {row.enabled ? t("disable") : t("enable")}
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {form ? (
        <form
          className="grid gap-3 rounded-md border border-border bg-bg p-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <h2 className="font-serif text-lg text-text md:col-span-2">{t("createTitle")}</h2>
          <label className="space-y-1 text-sm">
            <span>{t("fields.advertiserKind")}</span>
            <select
              className={inputClass}
              value={form.advertiser_kind}
              onChange={(event) =>
                set("advertiser_kind", event.target.value as Form["advertiser_kind"])
              }
            >
              {(["external", "business", "vendor"] as const).map((kind) => (
                <option key={kind} value={kind}>
                  {t(`kinds.${kind}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.advertiserName")}</span>
            <input
              className={inputClass}
              required
              minLength={2}
              maxLength={120}
              value={form.advertiser_name}
              onChange={(event) => set("advertiser_name", event.target.value)}
            />
          </label>
          {form.advertiser_kind === "vendor" ? (
            <label className="space-y-1 text-sm md:col-span-2">
              <span>{t("fields.vendorId")}</span>
              <input
                className={inputClass}
                required
                value={form.advertiser_vendor_id}
                onChange={(event) => set("advertiser_vendor_id", event.target.value)}
              />
            </label>
          ) : null}
          <label className="space-y-1 text-sm">
            <span>{t("fields.placementType")}</span>
            <select
              className={inputClass}
              value={form.placement_type}
              onChange={(event) =>
                set("placement_type", event.target.value as Form["placement_type"])
              }
            >
              {(["feed_slot", "carousel_slide"] as const).map((type) => (
                <option key={type} value={type}>
                  {t(`types.${type}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.imagePublicId")}</span>
            <input
              className={inputClass}
              required
              value={form.image_public_id}
              onChange={(event) => set("image_public_id", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.headline")}</span>
            <input
              className={inputClass}
              required
              maxLength={120}
              value={form.headline}
              onChange={(event) => set("headline", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.ctaLabel")}</span>
            <input
              className={inputClass}
              maxLength={40}
              value={form.cta_label}
              onChange={(event) => set("cta_label", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span>{t("fields.body")}</span>
            <textarea
              className={`${inputClass} min-h-20 py-2`}
              maxLength={280}
              value={form.body}
              onChange={(event) => set("body", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span>{t("fields.ctaHref")}</span>
            <input
              className={inputClass}
              required
              value={form.cta_href}
              placeholder={t("placeholders.path")}
              onChange={(event) => set("cta_href", event.target.value)}
            />
            <span className="text-xs text-muted">{t("ctaHint")}</span>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.startsAt")}</span>
            <input
              className={inputClass}
              type="datetime-local"
              required
              value={form.starts_at}
              onChange={(event) => set("starts_at", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.endsAt")}</span>
            <input
              className={inputClass}
              type="datetime-local"
              required
              value={form.ends_at}
              min={toLocalDatetime(new Date().toISOString())}
              onChange={(event) => set("ends_at", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.paidAmount")}</span>
            <input
              className={inputClass}
              inputMode="decimal"
              value={form.paid_amount}
              onChange={(event) => set("paid_amount", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.paymentReference")}</span>
            <input
              className={inputClass}
              pattern="[-._A-Za-z0-9]{1,80}"
              value={form.payment_reference}
              onChange={(event) => set("payment_reference", event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("fields.priority")}</span>
            <input
              className={inputClass}
              type="number"
              min={0}
              max={1000}
              value={form.priority}
              onChange={(event) => set("priority", event.target.value)}
            />
          </label>
          <div className="flex gap-2 md:col-span-2">
            <button
              type="submit"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm text-white"
            >
              {t("save")}
            </button>
            <button type="button" className={buttonClass} onClick={() => setForm(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
