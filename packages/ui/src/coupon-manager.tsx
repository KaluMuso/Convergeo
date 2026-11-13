"use client";

import { formatK } from "@vergeo/i18n";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { Badge } from "./badge";
import { Button } from "./button";
import { FormField } from "./form-field";
import { Input } from "./input";
import { Select } from "./select";

/**
 * Create / pause / archive coupons. One component for the admin app (platform-
 * funded coupons, any scope) and the vendor app (the shop's own coupons: whole
 * shop or one listing). All copy comes in through `labels` (next-intl in the
 * host app); money is typed in Kwacha and sent as integer ngwee.
 */
export type CouponManagerMode = "platform" | "vendor";

export type CouponRow = {
  id: string;
  code: string;
  title?: string | null;
  kind: "percent" | "fixed" | string;
  percent_bps?: number | null;
  amount_ngwee?: number | null;
  max_discount_ngwee?: number | null;
  scope: string;
  scope_id?: string | null;
  min_spend_ngwee: number;
  starts_at: string;
  ends_at?: string | null;
  total_limit?: number | null;
  per_user_limit: number;
  uses_count: number;
  status: "active" | "paused" | "archived" | string;
};

export type CouponManagerLabels = {
  title: string;
  intro: string;
  fundingNote: string;
  createTitle: string;
  code: string;
  codeHelp: string;
  kind: string;
  kindPercent: string;
  kindFixed: string;
  percent: string;
  amount: string;
  maxDiscount: string;
  maxDiscountHelp: string;
  minSpend: string;
  minSpendHelp: string;
  scope: string;
  scopeAll: string;
  scopeShop: string;
  scopeVendor: string;
  scopeCategory: string;
  scopeListing: string;
  scopeId: string;
  scopeIdHelp: string;
  startsOn: string;
  endsOn: string;
  endsOnHelp: string;
  totalLimit: string;
  totalLimitHelp: string;
  perUserLimit: string;
  create: string;
  creating: string;
  created: string;
  listTitle: string;
  empty: string;
  loading: string;
  /** "{used} used" / "{used} of {limit} used" */
  usage: string;
  usageLimited: string;
  /** "{value} off" */
  summaryOff: string;
  /** "min. {amount}" */
  summaryMin: string;
  statusActive: string;
  statusPaused: string;
  statusArchived: string;
  pause: string;
  resume: string;
  archive: string;
  errors: Record<string, string>;
};

type Props = {
  mode: CouponManagerMode;
  locale: string;
  labels: CouponManagerLabels;
  basePath: string;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
  /** Server error → translation key (last segment of `details.message_key`). */
  errorKeyOf?: (error: unknown) => string | null;
};

/** "12.50" → 1250 ngwee, exact (no float). Null when not a valid amount. */
export function kwachaToNgwee(input: string): number | null {
  const cleaned = input.replace(/[,\s]/g, "").replace(/^K/i, "");
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) return null;
  return Number(match[1]) * 100 + Number((match[2] ?? "0").padEnd(2, "0"));
}

/** "10" or "12.5" percent → basis points (1000 / 1250), exact. */
export function percentToBps(input: string): number | null {
  const match = /^(\d{1,3})(?:\.(\d{1,2}))?$/.exec(input.trim().replace("%", ""));
  if (!match) return null;
  const bps = Number(match[1]) * 100 + Number((match[2] ?? "0").padEnd(2, "0"));
  return bps >= 1 && bps <= 10_000 ? bps : null;
}

function fill(template: string, values: Record<string, string | number>): string {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.split(`{${key}}`).join(String(value)),
    template,
  );
}

function todayIso(): string {
  // Coupon dates are Lusaka calendar dates (UTC+2, no DST).
  return new Date(Date.now() + 2 * 3600_000).toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  code: "",
  kind: "percent",
  value: "",
  maxDiscount: "",
  minSpend: "",
  scope: "all",
  scopeId: "",
  startsOn: "",
  endsOn: "",
  totalLimit: "",
  perUserLimit: "1",
};

export function CouponManager({ mode, locale, labels, basePath, request, errorKeyOf }: Props) {
  const formId = useId();
  const [coupons, setCoupons] = useState<CouponRow[] | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM, startsOn: todayIso() });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const amountLocale = `${locale}-ZM`;
  const money = (ngwee: number) => formatK(ngwee, { locale: amountLocale });

  const errorText = useCallback(
    (error: unknown) => {
      const key = errorKeyOf?.(error) ?? null;
      return (key && labels.errors[key]) || labels.errors.generic || "";
    },
    [errorKeyOf, labels.errors],
  );

  const load = useCallback(async () => {
    try {
      const result = await request<{ coupons: CouponRow[] }>(basePath, { cache: "no-store" });
      setCoupons(Array.isArray(result?.coupons) ? result.coupons : []);
    } catch (error) {
      setCoupons([]);
      setMessage({ tone: "error", text: errorText(error) });
    }
  }, [basePath, errorText, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const set = (key: keyof typeof EMPTY_FORM) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const percent = form.kind === "percent" ? percentToBps(form.value) : null;
    const amount = form.kind === "fixed" ? kwachaToNgwee(form.value) : null;
    const minSpend = form.minSpend ? kwachaToNgwee(form.minSpend) : 0;
    const maxDiscount = form.maxDiscount ? kwachaToNgwee(form.maxDiscount) : null;
    if ((form.kind === "percent" && !percent) || (form.kind === "fixed" && !amount)) {
      setMessage({ tone: "error", text: labels.errors.amount ?? "" });
      return;
    }
    if (minSpend === null || (form.maxDiscount && !maxDiscount)) {
      setMessage({ tone: "error", text: labels.errors.amount ?? "" });
      return;
    }
    const body = {
      code: form.code.trim(),
      kind: form.kind,
      percent_bps: percent,
      amount_ngwee: amount,
      max_discount_ngwee: maxDiscount,
      min_spend_ngwee: minSpend,
      scope: mode === "vendor" && form.scope === "all" ? "vendor" : form.scope,
      scope_id:
        form.scope === "all" || (mode === "vendor" && form.scope === "vendor")
          ? null
          : form.scopeId.trim() || null,
      starts_on: form.startsOn,
      ends_on: form.endsOn || null,
      total_limit: form.totalLimit ? Number.parseInt(form.totalLimit, 10) : null,
      per_user_limit: Number.parseInt(form.perUserLimit || "1", 10),
    };
    setBusy(true);
    setMessage(null);
    try {
      await request<CouponRow>(basePath, { method: "POST", body: JSON.stringify(body) });
      setForm({ ...EMPTY_FORM, startsOn: todayIso() });
      setMessage({ tone: "ok", text: labels.created });
      await load();
    } catch (error) {
      setMessage({ tone: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const changeStatus = async (coupon: CouponRow, status: "active" | "paused" | "archived") => {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      await request<CouponRow>(`${basePath}/${coupon.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await load();
    } catch (error) {
      setMessage({ tone: "error", text: errorText(error) });
    } finally {
      setBusy(false);
    }
  };

  const scopeOptions =
    mode === "vendor"
      ? [
          ["vendor", labels.scopeShop],
          ["listing", labels.scopeListing],
        ]
      : [
          ["all", labels.scopeAll],
          ["vendor", labels.scopeVendor],
          ["category", labels.scopeCategory],
          ["listing", labels.scopeListing],
        ];
  const needsScopeId = form.scope !== "all" && !(mode === "vendor" && form.scope === "vendor");

  const summary = (coupon: CouponRow): string => {
    const value =
      coupon.kind === "percent" && coupon.percent_bps
        ? `${coupon.percent_bps / 100}%`
        : money(coupon.amount_ngwee ?? 0);
    const parts = [fill(labels.summaryOff, { value })];
    if (coupon.min_spend_ngwee > 0) {
      parts.push(fill(labels.summaryMin, { amount: money(coupon.min_spend_ngwee) }));
    }
    parts.push(
      coupon.total_limit
        ? fill(labels.usageLimited, { used: coupon.uses_count, limit: coupon.total_limit })
        : fill(labels.usage, { used: coupon.uses_count }),
    );
    return parts.join(" · ");
  };

  const statusLabel = (status: string) =>
    status === "active"
      ? labels.statusActive
      : status === "paused"
        ? labels.statusPaused
        : labels.statusArchived;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-display text-h2 text-display-ink">{labels.title}</h1>
        <p className="font-body text-sm text-text-2">{labels.intro}</p>
        <p className="font-body text-sm text-text-2">{labels.fundingNote}</p>
      </header>

      {message ? (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={`font-body text-sm ${message.tone === "error" ? "text-danger" : "text-success"}`}
        >
          {message.text}
        </p>
      ) : null}

      <form
        aria-labelledby={`${formId}-title`}
        onSubmit={(event) => void submit(event)}
        className="space-y-4 rounded-lg border border-border bg-surface p-4"
      >
        <h2 id={`${formId}-title`} className="font-display text-h3 text-display-ink">
          {labels.createTitle}
        </h2>
        <FormField label={labels.code} helpText={labels.codeHelp} required>
          <Input
            value={form.code}
            onChange={(event) => set("code")(event.target.value.toUpperCase())}
            maxLength={32}
            autoCapitalize="characters"
            required
          />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={labels.kind}>
            <Select value={form.kind} onChange={(event) => set("kind")(event.target.value)}>
              <option value="percent">{labels.kindPercent}</option>
              <option value="fixed">{labels.kindFixed}</option>
            </Select>
          </FormField>
          <FormField label={form.kind === "percent" ? labels.percent : labels.amount} required>
            <Input
              value={form.value}
              onChange={(event) => set("value")(event.target.value)}
              inputMode="decimal"
              required
            />
          </FormField>
          <FormField label={labels.minSpend} helpText={labels.minSpendHelp}>
            <Input
              value={form.minSpend}
              onChange={(event) => set("minSpend")(event.target.value)}
              inputMode="decimal"
            />
          </FormField>
          {form.kind === "percent" ? (
            <FormField label={labels.maxDiscount} helpText={labels.maxDiscountHelp}>
              <Input
                value={form.maxDiscount}
                onChange={(event) => set("maxDiscount")(event.target.value)}
                inputMode="decimal"
              />
            </FormField>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={labels.scope}>
            <Select
              value={mode === "vendor" && form.scope === "all" ? "vendor" : form.scope}
              onChange={(event) => set("scope")(event.target.value)}
            >
              {scopeOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </FormField>
          {needsScopeId ? (
            <FormField label={labels.scopeId} helpText={labels.scopeIdHelp} required>
              <Input
                value={form.scopeId}
                onChange={(event) => set("scopeId")(event.target.value)}
                required
              />
            </FormField>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={labels.startsOn} required>
            <Input
              type="date"
              value={form.startsOn}
              onChange={(event) => set("startsOn")(event.target.value)}
              required
            />
          </FormField>
          <FormField label={labels.endsOn} helpText={labels.endsOnHelp}>
            <Input
              type="date"
              value={form.endsOn}
              onChange={(event) => set("endsOn")(event.target.value)}
            />
          </FormField>
          <FormField label={labels.totalLimit} helpText={labels.totalLimitHelp}>
            <Input
              value={form.totalLimit}
              onChange={(event) => set("totalLimit")(event.target.value.replace(/\D/g, ""))}
              inputMode="numeric"
            />
          </FormField>
          <FormField label={labels.perUserLimit}>
            <Input
              value={form.perUserLimit}
              onChange={(event) => set("perUserLimit")(event.target.value.replace(/\D/g, ""))}
              inputMode="numeric"
            />
          </FormField>
        </div>
        <Button type="submit" loading={busy} loadingLabel={labels.creating}>
          {labels.create}
        </Button>
      </form>

      <section className="space-y-3" aria-labelledby={`${formId}-list`}>
        <h2 id={`${formId}-list`} className="font-display text-h3 text-display-ink">
          {labels.listTitle}
        </h2>
        {coupons === null ? (
          <p className="font-body text-sm text-text-2">{labels.loading}</p>
        ) : coupons.length === 0 ? (
          <p className="font-body text-sm text-text-2">{labels.empty}</p>
        ) : (
          <ul className="space-y-3">
            {coupons.map((coupon) => (
              <li
                key={coupon.id}
                className="space-y-2 rounded-lg border border-border bg-surface p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-base font-semibold text-display-ink">
                    {coupon.code}
                  </span>
                  <Badge
                    variant={
                      coupon.status === "active"
                        ? "in_stock"
                        : coupon.status === "paused"
                          ? "selling_fast"
                          : "out_of_stock"
                    }
                    label={statusLabel(coupon.status)}
                  />
                </div>
                <p className="font-body text-sm text-text-2">{summary(coupon)}</p>
                {coupon.status !== "archived" ? (
                  <div className="flex flex-wrap gap-2">
                    {coupon.status === "active" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        loadingLabel={labels.loading}
                        onClick={() => void changeStatus(coupon, "paused")}
                      >
                        {labels.pause}
                      </Button>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        loadingLabel={labels.loading}
                        onClick={() => void changeStatus(coupon, "active")}
                      >
                        {labels.resume}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      loadingLabel={labels.loading}
                      onClick={() => void changeStatus(coupon, "archived")}
                    >
                      {labels.archive}
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
