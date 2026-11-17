"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { emitToastKey } from "@vergeo/ui/src/toast";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi } from "./api";
import { ConfirmDiffDialog } from "./ConfirmDiffDialog";
import {
  ANALYTICS_DEPTHS,
  EMPTY_DRAFT,
  UUID_RE,
  draftToPayload,
  isValidPlanKey,
  overrideToPayload,
  planPatch,
  planToDraft,
  type OverrideForm,
  type PlanDraft,
  type PlanPayload,
  type VendorPlan,
  type VendorPlanDetail,
} from "./vendor-plans-api";

const INPUT = "min-h-11 w-full rounded-md border border-border bg-surface px-2 text-sm text-text";
const BUTTON = "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-sm";
const PRIMARY =
  "inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-surface";

function errorMessageKey(error: unknown): string {
  if (error instanceof ApiError && typeof error.details.message_key === "string") {
    const key = error.details.message_key;
    if (key.startsWith("admin.vendorPlans.")) return key.slice("admin.".length);
  }
  return "vendorPlans.errors.saveFailed";
}

type DraftFieldsProps = {
  draft: PlanDraft;
  onChange: (next: PlanDraft) => void;
  idPrefix: string;
};

function DraftFields({ draft, onChange, idPrefix }: DraftFieldsProps) {
  const t = useTranslations("admin");
  const field = (key: keyof PlanDraft, label: string, inputMode?: "decimal" | "numeric") => (
    <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor={`${idPrefix}-${key}`}>
      {label}
      <input
        id={`${idPrefix}-${key}`}
        className={INPUT}
        inputMode={inputMode}
        value={String(draft[key])}
        onChange={(event) => onChange({ ...draft, [key]: event.target.value })}
      />
    </label>
  );
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {field("name", t("vendorPlans.fields.name"))}
      {field("price", t("vendorPlans.fields.priceKwacha"), "decimal")}
      {field("maxListings", t("vendorPlans.fields.maxListings"), "numeric")}
      {field("maxImages", t("vendorPlans.fields.maxImages"), "numeric")}
      {field("featuredSlots", t("vendorPlans.fields.featuredSlots"), "numeric")}
      <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor={`${idPrefix}-depth`}>
        {t("vendorPlans.fields.analyticsDepth")}
        <select
          id={`${idPrefix}-depth`}
          className={INPUT}
          value={draft.analyticsDepth}
          onChange={(event) =>
            onChange({
              ...draft,
              analyticsDepth: event.target.value as PlanDraft["analyticsDepth"],
            })
          }
        >
          {ANALYTICS_DEPTHS.map((depth) => (
            <option key={depth} value={depth}>
              {t(`vendorPlans.depth.${depth}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-h-11 items-center gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={draft.wholesaleTools}
          onChange={(event) => onChange({ ...draft, wholesaleTools: event.target.checked })}
        />
        {t("vendorPlans.fields.wholesaleTools")}
      </label>
      <label className="flex min-h-11 items-center gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={draft.active}
          onChange={(event) => onChange({ ...draft, active: event.target.checked })}
        />
        {t("vendorPlans.fields.active")}
      </label>
    </div>
  );
}

export function VendorPlansEditor() {
  const t = useTranslations("admin");
  const locale = useLocale();
  const [plans, setPlans] = useState<VendorPlan[]>([]);
  const [drafts, setDrafts] = useState<Record<string, PlanDraft>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [newDraft, setNewDraft] = useState<PlanDraft>(EMPTY_DRAFT);
  const [pending, setPending] = useState<{
    plan: VendorPlan;
    patch: Partial<PlanPayload>;
  } | null>(null);

  const money = (ngwee: number) => formatK(ngwee, { locale });
  const limitText = (max: number | null) =>
    max === null ? t("vendorPlans.unlimited") : String(max);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const data = await configApi.request<VendorPlan[]>("/admin/vendor-plans");
      setPlans(data);
      setDrafts(Object.fromEntries(data.map((plan) => [plan.key, planToDraft(plan)])));
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setFormError(null);
    try {
      await action();
      emitToastKey("configSaved", { type: "success" });
      await load();
    } catch (caught) {
      setFormError(t(errorMessageKey(caught)));
      emitToastKey("actionFailed", { type: "error" });
    }
  };

  const requestSave = (plan: VendorPlan) => {
    const draft = drafts[plan.key];
    if (!draft) return;
    const result = draftToPayload(draft);
    if (!result.ok) {
      setFormError(t(`vendorPlans.errors.${result.error}`));
      return;
    }
    const patch = planPatch(plan, result.payload);
    if (Object.keys(patch).length === 0) return;
    setPending({ plan, patch });
  };

  const commitSave = async () => {
    if (!pending) return;
    const { plan, patch } = pending;
    await run(() =>
      configApi.request(`/admin/vendor-plans/${plan.key}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    );
    setPending(null);
  };

  const create = async () => {
    if (!isValidPlanKey(newDraft.key)) {
      setFormError(t("vendorPlans.errors.keyInvalid"));
      return;
    }
    const result = draftToPayload(newDraft);
    if (!result.ok) {
      setFormError(t(`vendorPlans.errors.${result.error}`));
      return;
    }
    await run(async () => {
      await configApi.request("/admin/vendor-plans", {
        method: "POST",
        body: JSON.stringify({ key: newDraft.key, ...result.payload, position: plans.length }),
      });
      setNewDraft(EMPTY_DRAFT);
    });
  };

  if (loading) return <p className="text-sm text-text-2">{t("config.common.loading")}</p>;
  if (loadError) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{t("config.common.error")}</p>
        <button type="button" className={BUTTON} onClick={() => void load()}>
          {t("config.common.retry")}
        </button>
      </div>
    );
  }

  const summary = (plan: VendorPlan, patch: Partial<PlanPayload>, side: "from" | "to") => {
    const merged = side === "from" ? plan : { ...plan, ...patch };
    return t("vendorPlans.summary", {
      price: money(merged.price_ngwee),
      listings: limitText(merged.max_listings),
      images: merged.max_images_per_listing,
    });
  };

  return (
    <div className="space-y-6" data-testid="vendor-plans-editor">
      <p className="text-sm text-text-2">{t("vendorPlans.hint")}</p>
      {formError ? (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      ) : null}

      <ul className="flex list-none flex-col gap-4 p-0">
        {plans.map((plan) => {
          const draft = drafts[plan.key] ?? planToDraft(plan);
          return (
            <li
              key={plan.key}
              className="space-y-3 rounded-md border border-border bg-surface p-4"
              data-testid={`vendor-plan-${plan.key}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-text">
                  {plan.name} <span className="font-mono text-xs text-text-2">{plan.key}</span>
                </p>
                <p className="flex gap-2 text-sm text-text-2">
                  {plan.is_default ? (
                    <span className="font-semibold text-primary">{t("vendorPlans.default")}</span>
                  ) : null}
                  <span>{t("vendorPlans.vendorCount", { count: plan.vendor_count })}</span>
                </p>
              </div>
              <DraftFields
                idPrefix={`plan-${plan.key}`}
                draft={draft}
                onChange={(next) => setDrafts((prev) => ({ ...prev, [plan.key]: next }))}
              />
              <div className="flex flex-wrap gap-2">
                <button type="button" className={PRIMARY} onClick={() => requestSave(plan)}>
                  {t("config.common.save")}
                </button>
                {!plan.is_default && plan.active ? (
                  <button
                    type="button"
                    className={BUTTON}
                    onClick={() =>
                      void run(() =>
                        configApi.request(`/admin/vendor-plans/${plan.key}`, {
                          method: "PATCH",
                          body: JSON.stringify({ is_default: true }),
                        }),
                      )
                    }
                  >
                    {t("vendorPlans.makeDefault")}
                  </button>
                ) : null}
                {!plan.is_default && plan.vendor_count === 0 ? (
                  <button
                    type="button"
                    className={`${BUTTON} text-danger`}
                    onClick={() =>
                      void run(() =>
                        configApi.request(`/admin/vendor-plans/${plan.key}`, { method: "DELETE" }),
                      )
                    }
                  >
                    {t("vendorPlans.delete")}
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>

      <section className="space-y-3 rounded-md border border-border p-4">
        <h3 className="font-semibold text-text">{t("vendorPlans.createHeading")}</h3>
        <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor="new-plan-key">
          {t("vendorPlans.fields.key")}
          <input
            id="new-plan-key"
            className={`${INPUT} font-mono`}
            value={newDraft.key}
            onChange={(event) => setNewDraft({ ...newDraft, key: event.target.value.trim() })}
          />
        </label>
        <DraftFields idPrefix="new-plan" draft={newDraft} onChange={setNewDraft} />
        <button type="button" className={PRIMARY} onClick={() => void create()}>
          {t("vendorPlans.create")}
        </button>
      </section>

      <VendorPlanAssignment plans={plans} />

      <ConfirmDiffDialog
        open={pending !== null}
        dangerous
        fromLabel={t("config.confirm.from")}
        toLabel={t("config.confirm.to")}
        fromValue={pending ? summary(pending.plan, pending.patch, "from") : ""}
        toValue={pending ? summary(pending.plan, pending.patch, "to") : ""}
        onCancel={() => setPending(null)}
        onConfirm={commitSave}
      />
    </div>
  );
}

const EMPTY_OVERRIDE: OverrideForm = {
  unlimited: false,
  maxListings: "",
  maxImages: "",
  expiresOn: "",
  reason: "",
};

function VendorPlanAssignment({ plans }: { plans: VendorPlan[] }) {
  const t = useTranslations("admin");
  const [vendorId, setVendorId] = useState("");
  const [detail, setDetail] = useState<VendorPlanDetail | null>(null);
  const [planKey, setPlanKey] = useState("");
  const [note, setNote] = useState("");
  const [override, setOverride] = useState<OverrideForm>(EMPTY_OVERRIDE);
  const [error, setError] = useState<string | null>(null);

  const base = `/admin/vendors/${vendorId.trim()}/plan`;

  const act = async (action: () => Promise<VendorPlanDetail>) => {
    setError(null);
    try {
      const next = await action();
      setDetail(next);
      setPlanKey(next.assignment?.plan_key ?? "");
      emitToastKey("configSaved", { type: "success" });
    } catch (caught) {
      setError(t(errorMessageKey(caught)));
    }
  };

  const lookup = async () => {
    if (!UUID_RE.test(vendorId.trim())) {
      setError(t("vendorPlans.errors.vendorIdInvalid"));
      return;
    }
    setError(null);
    try {
      const next = await configApi.request<VendorPlanDetail>(base);
      setDetail(next);
      setPlanKey(next.assignment?.plan_key ?? "");
    } catch {
      setDetail(null);
      setError(t("vendorPlans.errors.vendorNotFound"));
    }
  };

  const saveOverride = () => {
    const result = overrideToPayload(override);
    if (!result.ok) {
      setError(t(`vendorPlans.errors.${result.error}`));
      return;
    }
    void act(() =>
      configApi.request<VendorPlanDetail>(`${base}/override`, {
        method: "PUT",
        body: JSON.stringify(result.payload),
      }),
    );
  };

  const limitText = (max: number | null) =>
    max === null ? t("vendorPlans.unlimited") : String(max);

  return (
    <section
      className="space-y-3 rounded-md border border-border p-4"
      data-testid="vendor-plan-assign"
    >
      <h3 className="font-semibold text-text">{t("vendorPlans.vendor.heading")}</h3>
      <p className="text-sm text-text-2">{t("vendorPlans.vendor.hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-1 flex-col gap-1 text-xs text-text-2" htmlFor="plan-vendor-id">
          {t("vendorPlans.vendor.vendorId")}
          <input
            id="plan-vendor-id"
            className={`${INPUT} font-mono`}
            value={vendorId}
            onChange={(event) => setVendorId(event.target.value)}
          />
        </label>
        <button type="button" className={BUTTON} onClick={() => void lookup()}>
          {t("vendorPlans.vendor.load")}
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {detail ? (
        <div className="space-y-4">
          {!detail.flag_enabled ? (
            <p className="text-sm text-warning">{t("vendorPlans.vendor.flagOff")}</p>
          ) : null}
          <p className="text-sm text-text">
            {t("vendorPlans.vendor.effective", {
              plan: detail.effective_plan_key ?? t("vendorPlans.vendor.none"),
              listings: limitText(detail.effective_max_listings),
              count: detail.listing_count,
              images: detail.effective_max_images_per_listing ?? 8,
            })}
          </p>

          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor="plan-assign-key">
              {t("vendorPlans.vendor.plan")}
              <select
                id="plan-assign-key"
                className={INPUT}
                value={planKey}
                onChange={(event) => setPlanKey(event.target.value)}
              >
                <option value="">{t("vendorPlans.vendor.defaultPlan")}</option>
                {plans
                  .filter((plan) => plan.active)
                  .map((plan) => (
                    <option key={plan.key} value={plan.key}>
                      {plan.name}
                    </option>
                  ))}
              </select>
            </label>
            <label
              className="flex flex-1 flex-col gap-1 text-xs text-text-2"
              htmlFor="plan-assign-note"
            >
              {t("vendorPlans.vendor.note")}
              <input
                id="plan-assign-note"
                className={INPUT}
                maxLength={500}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <button
              type="button"
              className={PRIMARY}
              disabled={!planKey}
              onClick={() =>
                void act(() =>
                  configApi.request<VendorPlanDetail>(base, {
                    method: "PUT",
                    body: JSON.stringify({ plan_key: planKey, note: note.trim() || null }),
                  }),
                )
              }
            >
              {t("vendorPlans.vendor.assign")}
            </button>
          </div>
          <p className="text-xs text-text-2">{t("vendorPlans.vendor.noBilling")}</p>

          <div className="space-y-2 rounded-md border border-border p-3">
            <h4 className="text-sm font-semibold text-text">{t("vendorPlans.override.heading")}</h4>
            {detail.override ? (
              <p className="text-sm text-text">
                {t(
                  detail.override.live
                    ? "vendorPlans.override.current"
                    : "vendorPlans.override.expired",
                  {
                    listings: detail.override.unlimited_listings
                      ? t("vendorPlans.unlimited")
                      : limitText(detail.override.max_listings),
                    expires: detail.override.expires_at.slice(0, 10),
                    reason: detail.override.reason,
                  },
                )}
              </p>
            ) : null}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label className="flex min-h-11 items-center gap-2 text-sm text-text">
                <input
                  type="checkbox"
                  checked={override.unlimited}
                  onChange={(event) =>
                    setOverride({ ...override, unlimited: event.target.checked })
                  }
                />
                {t("vendorPlans.override.unlimited")}
              </label>
              <label
                className="flex flex-col gap-1 text-xs text-text-2"
                htmlFor="override-listings"
              >
                {t("vendorPlans.fields.maxListings")}
                <input
                  id="override-listings"
                  className={INPUT}
                  inputMode="numeric"
                  disabled={override.unlimited}
                  value={override.maxListings}
                  onChange={(event) =>
                    setOverride({ ...override, maxListings: event.target.value })
                  }
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor="override-images">
                {t("vendorPlans.fields.maxImages")}
                <input
                  id="override-images"
                  className={INPUT}
                  inputMode="numeric"
                  value={override.maxImages}
                  onChange={(event) => setOverride({ ...override, maxImages: event.target.value })}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor="override-expires">
                {t("vendorPlans.override.expiresOn")}
                <input
                  id="override-expires"
                  type="date"
                  className={INPUT}
                  value={override.expiresOn}
                  onChange={(event) => setOverride({ ...override, expiresOn: event.target.value })}
                />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-xs text-text-2" htmlFor="override-reason">
              {t("vendorPlans.override.reason")}
              <input
                id="override-reason"
                className={INPUT}
                maxLength={500}
                value={override.reason}
                onChange={(event) => setOverride({ ...override, reason: event.target.value })}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={PRIMARY} onClick={saveOverride}>
                {t("vendorPlans.override.save")}
              </button>
              {detail.override ? (
                <button
                  type="button"
                  className={`${BUTTON} text-danger`}
                  onClick={() =>
                    void act(() =>
                      configApi.request<VendorPlanDetail>(`${base}/override`, { method: "DELETE" }),
                    )
                  }
                >
                  {t("vendorPlans.override.remove")}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
