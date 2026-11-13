"use client";

import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  listAdvanceDebts,
  recordAdvanceRepayment,
  type AdvanceDebt,
  type AdvanceDebtStatus,
} from "./api";
import { kwachaToNgwee, REPAYMENT_REFERENCE_PATTERN } from "./money";

const STATUSES: AdvanceDebtStatus[] = ["open", "settled", "written_off"];

type RepayDraft = { vendorId: string; amount: string; reference: string };

const EMPTY_DRAFT: RepayDraft = { vendorId: "", amount: "", reference: "" };

export function AdvanceDebts() {
  const t = useTranslations("admin.events.advanceDebts");
  const format = useFormatter();
  const [status, setStatus] = useState<AdvanceDebtStatus | "">("open");
  const [vendorFilter, setVendorFilter] = useState("");
  const [appliedVendor, setAppliedVendor] = useState("");
  const [items, setItems] = useState<AdvanceDebt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<RepayDraft>(EMPTY_DRAFT);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await listAdvanceDebts({
        status,
        vendorId: appliedVendor,
      });
      setItems(payload.items);
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 403 ? t("forbidden") : t("error"));
    } finally {
      setLoading(false);
    }
  }, [appliedVendor, status, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const submitRepayment = async () => {
    setFormError(null);
    setNotice(null);
    const amountNgwee = kwachaToNgwee(draft.amount);
    if (!draft.vendorId.trim()) {
      setFormError(t("form.vendorRequired"));
      return;
    }
    if (amountNgwee === null) {
      setFormError(t("form.amountInvalid"));
      return;
    }
    if (!REPAYMENT_REFERENCE_PATTERN.test(draft.reference.trim())) {
      setFormError(t("form.referenceInvalid"));
      return;
    }
    setSaving(true);
    try {
      const result = await recordAdvanceRepayment({
        vendor_id: draft.vendorId.trim(),
        amount_ngwee: amountNgwee,
        reference: draft.reference.trim(),
      });
      setNotice(t("form.saved", { remaining: formatK(result.receivable_ngwee) }));
      setDraft(EMPTY_DRAFT);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "repayment_exceeds_receivable") {
        setFormError(t("form.exceeds"));
      } else {
        setFormError(t("form.failed"));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-4" aria-labelledby="advance-debts-title">
      <header className="space-y-1">
        <h2 id="advance-debts-title" className="font-serif text-lg text-text">
          {t("title")}
        </h2>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setAppliedVendor(vendorFilter.trim());
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          {t("filters.status")}
          <select
            className="min-h-11 rounded-md border border-border px-2 text-sm"
            value={status}
            onChange={(event) => setStatus(event.target.value as AdvanceDebtStatus | "")}
          >
            <option value="">{t("filters.all")}</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`status.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1 text-sm">
          {t("filters.organiser")}
          <input
            className="min-h-11 rounded-md border border-border px-2 font-mono text-sm"
            value={vendorFilter}
            placeholder={t("filters.organiserPlaceholder")}
            onChange={(event) => setVendorFilter(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-sm font-semibold"
        >
          {t("filters.apply")}
        </button>
      </form>

      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((debt) => (
            <li key={debt.id} className="space-y-1 rounded-lg border border-border bg-surface p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{debt.vendor_name || debt.vendor_id}</p>
                <span className="rounded border border-border px-2 py-0.5 text-xs">
                  {t(`status.${debt.status}`)}
                </span>
              </div>
              <p className="text-sm text-muted">{t("event", { title: debt.event_title })}</p>
              <p className="text-sm">
                {t("amounts", {
                  outstanding: formatK(debt.outstanding_ngwee),
                  amount: formatK(debt.amount_ngwee),
                })}
              </p>
              <p className="text-sm text-muted">
                {t("due", {
                  date: format.dateTime(new Date(debt.due_at), {
                    dateStyle: "medium",
                  }),
                })}
              </p>
              {debt.blacklisted_at ? (
                <p className="text-sm text-danger">{t("blacklisted")}</p>
              ) : null}
              {debt.status === "open" ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center text-sm font-semibold text-primary underline"
                  onClick={() =>
                    setDraft({
                      vendorId: debt.vendor_id,
                      amount: "",
                      reference: "",
                    })
                  }
                >
                  {t("form.useOrganiser")}
                </button>
              ) : null}
              <p className="font-mono text-xs text-muted">{debt.vendor_id}</p>
            </li>
          ))}
        </ul>
      )}

      <form
        className="space-y-2 rounded-lg border border-border bg-surface p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submitRepayment();
        }}
      >
        <h3 className="font-medium">{t("form.title")}</h3>
        <p className="text-sm text-muted">{t("form.hint")}</p>
        <label className="flex flex-col gap-1 text-sm">
          {t("form.organiser")}
          <input
            className="min-h-11 rounded-md border border-border px-2 font-mono text-sm"
            value={draft.vendorId}
            onChange={(event) => setDraft((prev) => ({ ...prev, vendorId: event.target.value }))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("form.amount")}
          <input
            inputMode="decimal"
            className="min-h-11 rounded-md border border-border px-2 font-mono text-sm"
            value={draft.amount}
            onChange={(event) => setDraft((prev) => ({ ...prev, amount: event.target.value }))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("form.reference")}
          <input
            className="min-h-11 rounded-md border border-border px-2 font-mono text-sm"
            value={draft.reference}
            onChange={(event) => setDraft((prev) => ({ ...prev, reference: event.target.value }))}
          />
        </label>
        {formError ? (
          <p className="text-sm text-danger" role="alert">
            {formError}
          </p>
        ) : null}
        {notice ? (
          <p className="text-sm text-success" role="status">
            {notice}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={saving}
          className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-sm font-semibold text-[var(--primary-btn-fg)] disabled:opacity-50"
        >
          {saving ? t("form.saving") : t("form.submit")}
        </button>
      </form>
    </section>
  );
}
