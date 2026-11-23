"use client";

import { formatK } from "@vergeo/i18n";
import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { classifyAdminRequestError } from "../../_components/admin-request";
import { ConfirmModal } from "../../_components/ConfirmModal";
import { CopyButton } from "../../_components/CopyButton";
import { EmptyBlock, LoadingBlock } from "../../_components/StateBlocks";
import {
  feedAdminApi,
  ngweeToKwachaInput,
  parseKwachaToNgwee,
} from "../../home-feed/_components/feed-admin-api";

import {
  fromLusakaInput,
  isEditable,
  isValidReason,
  isValidWindow,
  TARGET_KINDS,
  toLusakaInput,
  type AdTarget,
  type TargetKind,
} from "./ad-helpers";

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
  target_kind?: TargetKind | null;
  target_id?: string | null;
  target_visible?: boolean;
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
  id: string | null;
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
  target: AdTarget | null;
  /** Edit mode: target that was set when the form opened (id only). */
  initial_target: { kind: TargetKind; id: string } | null;
};

const EMPTY_FORM: Form = {
  id: null,
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
  target: null,
  initial_target: null,
};

function formFromPlacement(row: Placement): Form {
  return {
    id: row.id,
    advertiser_kind: row.advertiser_kind,
    advertiser_vendor_id: row.advertiser_vendor_id ?? "",
    advertiser_name: row.advertiser_name,
    placement_type: row.placement_type,
    image_public_id: row.image_public_id,
    headline: row.headline,
    body: row.body ?? "",
    cta_label: row.cta_label ?? "",
    cta_href: row.cta_href,
    starts_at: toLusakaInput(row.starts_at),
    ends_at: toLusakaInput(row.ends_at),
    priority: String(row.priority),
    paid_amount: ngweeToKwachaInput(row.paid_amount_ngwee),
    payment_reference: row.payment_reference ?? "",
    target: null,
    initial_target:
      row.target_kind && row.target_id ? { kind: row.target_kind, id: row.target_id } : null,
  };
}

const inputClass = "min-h-11 w-full rounded-md border border-border bg-bg px-3 text-sm text-text";
const buttonClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-text";
const primaryClass =
  "inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)]";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; permission: boolean }
  | { kind: "ready"; rows: Placement[] };

export function AdvertisingBoard({ locale }: { locale: string }) {
  const t = useTranslations("admin.advertising");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [form, setForm] = useState<Form | null>(null);
  const [removing, setRemoving] = useState<Placement | null>(null);
  const [removeReason, setRemoveReason] = useState("");
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [targetKind, setTargetKind] = useState<TargetKind | "">("");
  const [targetQuery, setTargetQuery] = useState("");
  const [targetResults, setTargetResults] = useState<AdTarget[] | null>(null);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const rows = await feedAdminApi.request<Placement[]>("/admin/ads/placements", {
        cache: "no-store",
      });
      setState({ kind: "ready", rows: Array.isArray(rows) ? rows : [] });
    } catch (error) {
      setState({
        kind: "error",
        permission: classifyAdminRequestError(error).kind === "permission",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openForm = (next: Form) => {
    setForm(next);
    setTargetKind(next.initial_target?.kind ?? "");
    setTargetQuery("");
    setTargetResults(null);
  };

  const searchTargets = async () => {
    if (!targetKind) return;
    setSearching(true);
    try {
      const params = new URLSearchParams({ kind: targetKind, q: targetQuery.trim() });
      setTargetResults(
        await feedAdminApi.request<AdTarget[]>(`/admin/ads/targets?${params.toString()}`),
      );
    } catch {
      setTargetResults([]);
      notify.error(t("saveError"));
    } finally {
      setSearching(false);
    }
  };

  const save = async () => {
    if (!form) return;
    const paid = parseKwachaToNgwee(form.paid_amount || "0");
    const startsAt = fromLusakaInput(form.starts_at);
    const endsAt = fromLusakaInput(form.ends_at);
    if (paid === null) {
      notify.error(t("errors.invalidAmount"));
      return;
    }
    if (!isValidWindow(startsAt, endsAt)) {
      notify.error(t("errors.invalidWindow"));
      return;
    }
    const common = {
      advertiser_name: form.advertiser_name.trim(),
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
    };
    const target = form.target ? { target_kind: form.target.kind, target_id: form.target.id } : {};
    try {
      if (form.id) {
        const clear = !form.target && form.initial_target && !targetKind;
        await feedAdminApi.request(`/admin/ads/placements/${form.id}`, {
          method: "PATCH",
          body: JSON.stringify({ ...common, ...target, ...(clear ? { clear_target: true } : {}) }),
        });
        notify.success(t("updated"));
      } else {
        await feedAdminApi.request("/admin/ads/placements", {
          method: "POST",
          body: JSON.stringify({
            ...common,
            ...target,
            advertiser_kind: form.advertiser_kind,
            advertiser_vendor_id: form.advertiser_vendor_id.trim() || null,
            placement_type: form.placement_type,
          }),
        });
        notify.success(t("created"));
      }
      setForm(null);
      await load();
    } catch (error) {
      const code = (error as { code?: string } | null)?.code;
      notify.error(
        code === "ad_target_not_visible" ? t("errors.targetNotVisible") : t("saveError"),
      );
    }
  };

  const transition = async (row: Placement, toStatus: PlacementStatus) => {
    if (toStatus === "ended") {
      setRemoving(row);
      setRemoveReason("");
      setRemoveError(null);
      return;
    }
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

  const remove = async (): Promise<boolean> => {
    if (!removing) return false;
    try {
      await feedAdminApi.request(`/admin/ads/placements/${removing.id}/transition`, {
        method: "POST",
        body: JSON.stringify({ to_status: "ended", reason: removeReason.trim() }),
      });
      notify.success(t("removed"));
      await load();
      return true;
    } catch {
      setRemoveError(t("transitionError"));
      return false;
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

  if (state.kind === "loading") return <LoadingBlock label={t("loading")} />;
  if (state.kind === "error")
    return (
      <AdminLoadFailure
        permissionDenied={state.permission}
        message={t("loadError")}
        retryLabel={t("retry")}
        onRetry={() => void load()}
      />
    );
  const rows = state.rows;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={primaryClass} onClick={() => openForm({ ...EMPTY_FORM })}>
          {t("create")}
        </button>
        <p className="text-xs text-muted">
          {t("hint")} {t("lusakaTime")}
        </p>
      </div>

      {rows.length === 0 ? <EmptyBlock title={t("empty")} body={t("emptyBody")} /> : null}

      {rows.length > 0 ? (
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
                    {row.target_kind ? (
                      <div className="text-xs text-muted">
                        {t("targetLabel", { kind: t(`targetKinds.${row.target_kind}`) })}
                      </div>
                    ) : null}
                    {row.target_visible === false && row.status !== "ended" ? (
                      <p className="mt-1 text-xs font-medium text-warning" role="status">
                        {t("targetHidden")}
                      </p>
                    ) : null}
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
                          className={`${buttonClass} ${next === "ended" ? "border-danger text-danger" : ""}`}
                          onClick={() => void transition(row, next)}
                        >
                          {next === "ended" ? t("remove") : t(`actions.${next}`)}
                        </button>
                      ))}
                      {isEditable(row.status) ? (
                        <>
                          <button
                            type="button"
                            className={buttonClass}
                            onClick={() => openForm(formFromPlacement(row))}
                          >
                            {t("edit")}
                          </button>
                          <button
                            type="button"
                            className={buttonClass}
                            onClick={() => void toggle(row)}
                          >
                            {row.enabled ? t("disable") : t("enable")}
                          </button>
                        </>
                      ) : null}
                      <CopyButton value={row.id} label={t("copyId")} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {form ? (
        <form
          className="grid gap-3 rounded-md border border-border bg-bg p-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <h2 className="font-serif text-lg text-text md:col-span-2">
            {form.id ? t("editTitle") : t("createTitle")}
          </h2>
          {!form.id ? (
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
          ) : null}
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
          {!form.id && form.advertiser_kind === "vendor" ? (
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
          {!form.id ? (
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
          ) : null}

          <fieldset className="space-y-2 rounded-md border border-border p-3 md:col-span-2">
            <legend className="px-1 text-sm font-medium text-text">{t("target.title")}</legend>
            <p className="text-xs text-muted">{t("target.hint")}</p>
            <div className="flex flex-wrap items-end gap-2">
              <label className="space-y-1 text-sm">
                <span>{t("target.kind")}</span>
                <select
                  className={inputClass}
                  value={targetKind}
                  onChange={(event) => {
                    setTargetKind(event.target.value as TargetKind | "");
                    setTargetResults(null);
                    set("target", null);
                  }}
                >
                  <option value="">{t("target.none")}</option>
                  {TARGET_KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {t(`targetKinds.${kind}`)}
                    </option>
                  ))}
                </select>
              </label>
              {targetKind ? (
                <>
                  <label className="min-w-0 flex-1 space-y-1 text-sm">
                    <span>{t("target.search")}</span>
                    <input
                      className={inputClass}
                      value={targetQuery}
                      maxLength={80}
                      onChange={(event) => setTargetQuery(event.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className={buttonClass}
                    disabled={searching}
                    onClick={() => void searchTargets()}
                  >
                    {searching ? t("target.searching") : t("target.searchButton")}
                  </button>
                </>
              ) : null}
            </div>
            {form.target ? (
              <p className="text-sm text-text" data-testid="ad-target-selected">
                {t("target.selected", { label: form.target.label })}
              </p>
            ) : null}
            {targetResults && targetResults.length === 0 ? (
              <p className="text-xs text-muted">{t("target.noResults")}</p>
            ) : null}
            {targetResults && targetResults.length > 0 ? (
              <ul className="max-h-56 space-y-1 overflow-y-auto">
                {targetResults.map((result) => (
                  <li
                    key={result.id}
                    className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1 text-sm"
                  >
                    <span className="min-w-0 truncate">
                      {result.label}
                      {!result.visible ? (
                        <span className="ml-2 text-xs text-warning">{t("target.unavailable")}</span>
                      ) : null}
                    </span>
                    <button
                      type="button"
                      className={buttonClass}
                      disabled={!result.visible}
                      onClick={() => {
                        setForm((current) =>
                          current ? { ...current, target: result, cta_href: result.href } : current,
                        );
                        setTargetResults(null);
                      }}
                    >
                      {t("target.use")}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </fieldset>

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
              onChange={(event) => set("ends_at", event.target.value)}
            />
          </label>
          <p className="text-xs text-muted md:col-span-2">{t("lusakaTime")}</p>
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
            <button type="submit" className={primaryClass}>
              {form.id ? t("saveChanges") : t("save")}
            </button>
            <button type="button" className={buttonClass} onClick={() => setForm(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}

      {removing ? (
        <ConfirmModal
          open
          destructive
          data-testid="ad-remove-confirm"
          title={t("removeTitle")}
          summary={t("removeSummary", { headline: removing.headline })}
          confirmLabel={t("remove")}
          canConfirm={isValidReason(removeReason)}
          error={removeError}
          onConfirm={remove}
          onClose={() => setRemoving(null)}
        >
          <label className="block space-y-1 text-sm">
            <span>{t("reasonLabel")}</span>
            <textarea
              className={`${inputClass} min-h-16 py-2`}
              maxLength={500}
              value={removeReason}
              placeholder={t("reasonPlaceholder")}
              onChange={(event) => setRemoveReason(event.target.value)}
            />
          </label>
        </ConfirmModal>
      ) : null}
    </div>
  );
}
