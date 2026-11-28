"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { glassClass } from "@vergeo/ui/src/glass";
import { Input } from "@vergeo/ui/src/input";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { VendorPageSkeleton } from "../../_components/page-skeleton";
import {
  EMPTY_FORM,
  OPEN_STATUSES,
  toRequestBody,
  type ImportFormValues,
  type ImportQuote,
  type ImportRequest,
} from "../_lib/import-requests";
import { sourceErrorKey, useSourceApi } from "../_lib/use-source-api";

/**
 * The Import tab: the vendor's own import requests and the request form. A request
 * is data only: our team replies with an ESTIMATED landed cost in ZMW. No payment,
 * no order, nothing is charged.
 */
export function ImportPanel() {
  const t = useTranslations("vendor.source");
  const { client, ready } = useSourceApi();
  const [requests, setRequests] = useState<ImportRequest[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [values, setValues] = useState<ImportFormValues>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);

  const load = useCallback(() => {
    client
      .request<ImportRequest[]>("/vendor/sourcing/import-requests")
      .then((rows) => {
        setRequests(rows);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [client]);

  useEffect(() => {
    if (ready) load();
  }, [ready, load]);

  async function submit() {
    const body = toRequestBody(values);
    if (body === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setBusy(true);
    setMessage(null);
    try {
      await client.request("/vendor/sourcing/import-requests", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessage(t("import.sent"));
      setValues(EMPTY_FORM);
      setFormOpen(false);
      load();
    } catch (error) {
      setMessage(t(sourceErrorKey(error)));
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id: string) {
    setBusy(true);
    setMessage(null);
    try {
      await client.request(`/vendor/sourcing/import-requests/${id}/cancel`, {
        method: "POST",
      });
      load();
    } catch (error) {
      setMessage(t(sourceErrorKey(error)));
    } finally {
      setBusy(false);
    }
  }

  const set = (key: keyof ImportFormValues) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  return (
    <section className="space-y-4" aria-labelledby="import-heading">
      <div className="space-y-1">
        <h2 id="import-heading" className="m-0 text-lg font-semibold text-text">
          {t("import.heading")}
        </h2>
        <p className="m-0 text-sm text-text-2">{t("import.howItWorks")}</p>
        <p className="m-0 text-sm font-medium text-text">{t("import.estimateNotice")}</p>
      </div>
      <Button type="button" loadingLabel={t("loading")} onClick={() => setFormOpen(true)}>
        {t("import.newRequest")}
      </Button>
      {message ? (
        <p role="status" className="m-0 text-sm text-text">
          {message}
        </p>
      ) : null}

      {formOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="import-form-title"
          className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
        >
          <form
            className={`${glassClass("overlay")} max-h-[92vh] w-full max-w-lg space-y-3 overflow-y-auto p-4`}
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <h3 id="import-form-title" className="m-0 text-base font-semibold text-text">
              {t("import.newRequest")}
            </h3>
            <Field id="imp-title" label={t("import.fields.title")}>
              <Input
                id="imp-title"
                value={values.title}
                maxLength={120}
                onChange={(e) => set("title")(e.target.value)}
              />
            </Field>
            <Field id="imp-desc" label={t("import.fields.description")}>
              <textarea
                id="imp-desc"
                value={values.description}
                maxLength={2000}
                onChange={(e) => set("description")(e.target.value)}
                className="min-h-20 w-full rounded-md border border-border bg-surface p-3 text-body text-text"
              />
            </Field>
            <Field id="imp-url" label={t("import.fields.referenceUrl")}>
              <Input
                id="imp-url"
                type="url"
                value={values.referenceUrl}
                maxLength={500}
                onChange={(e) => set("referenceUrl")(e.target.value)}
              />
            </Field>
            <Field id="imp-img" label={t("import.fields.imageUrls")}>
              <textarea
                id="imp-img"
                value={values.imageUrls}
                onChange={(e) => set("imageUrls")(e.target.value)}
                className="min-h-16 w-full rounded-md border border-border bg-surface p-3 text-body text-text"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field id="imp-qty" label={t("import.fields.quantity")}>
                <Input
                  id="imp-qty"
                  inputMode="numeric"
                  value={values.quantity}
                  onChange={(e) => set("quantity")(e.target.value)}
                />
              </Field>
              <Field id="imp-unit" label={t("import.fields.unit")}>
                <Input
                  id="imp-unit"
                  value={values.unit}
                  maxLength={20}
                  onChange={(e) => set("unit")(e.target.value)}
                />
              </Field>
              <Field id="imp-price" label={t("import.fields.targetPrice")}>
                <Input
                  id="imp-price"
                  inputMode="decimal"
                  value={values.targetPrice}
                  onChange={(e) => set("targetPrice")(e.target.value)}
                />
              </Field>
              <Field id="imp-city" label={t("import.fields.destination")}>
                <Input
                  id="imp-city"
                  value={values.destination}
                  maxLength={60}
                  onChange={(e) => set("destination")(e.target.value)}
                />
              </Field>
            </div>
            {invalid ? (
              <p role="alert" className="m-0 text-sm text-danger">
                {t("errors.generic")}
              </p>
            ) : null}
            <p className="m-0 text-micro text-text-2">{t("import.estimateNotice")}</p>
            <div className="flex gap-2">
              <Button type="submit" loading={busy} loadingLabel={t("import.submitting")}>
                {t("import.submit")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                loadingLabel=""
                onClick={() => setFormOpen(false)}
              >
                {t("import.close")}
              </Button>
            </div>
          </form>
        </div>
      ) : null}

      {failed ? (
        <p role="alert" className="text-sm text-text-2">
          {t("errors.load")}
        </p>
      ) : requests === null ? (
        <VendorPageSkeleton rows={2} label={t("loading")} />
      ) : requests.length === 0 ? (
        <p className="text-sm text-text-2">{t("import.empty")}</p>
      ) : (
        <ul className="m-0 list-none space-y-3 p-0" data-testid="import-requests">
          {requests.map((request) => (
            <RequestCard
              key={request.id}
              request={request}
              busy={busy}
              onCancel={() => void cancel(request.id)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm text-text">
        {label}
      </label>
      {children}
    </div>
  );
}

function RequestCard({
  request,
  busy,
  onCancel,
}: {
  request: ImportRequest;
  busy: boolean;
  onCancel: () => void;
}) {
  const t = useTranslations("vendor.source");
  return (
    <li
      className="space-y-2 rounded-lg border border-border bg-surface p-4 shadow-1"
      data-testid={`import-${request.id}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="m-0 text-base font-semibold text-text">{request.title}</h3>
        <span className="text-sm font-medium text-text">
          {t(`import.status.${request.status}`)}
        </span>
      </div>
      <p className="m-0 text-sm text-text-2">
        {t("import.qtyLine", { qty: request.quantity, unit: request.unit })}
        {request.target_unit_price_ngwee !== null
          ? ` · ${t("import.target", { price: formatK(request.target_unit_price_ngwee) })}`
          : ""}
      </p>
      {request.latest_quote ? <QuoteLines quote={request.latest_quote} /> : null}
      {OPEN_STATUSES.has(request.status) ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          loading={busy}
          loadingLabel={t("loading")}
          onClick={onCancel}
        >
          {t("import.cancel")}
        </Button>
      ) : null}
    </li>
  );
}

function QuoteLines({ quote }: { quote: ImportQuote }) {
  const t = useTranslations("vendor.source");
  const lines: Array<[string, number]> = [
    [t("import.quote.product"), quote.product_ngwee],
    [t("import.quote.freight"), quote.freight_ngwee],
    [t("import.quote.duty"), quote.duty_ngwee],
    [t("import.quote.clearing"), quote.clearing_ngwee],
  ];
  if (quote.other_ngwee > 0) lines.push([t("import.quote.other"), quote.other_ngwee]);
  return (
    <div className="space-y-1 rounded-md bg-bg-2 p-3" data-testid="import-quote">
      <p className="m-0 text-sm font-semibold text-text">
        {t("import.quote.title")} ({t("import.quote.label")})
      </p>
      <dl className="m-0 space-y-0.5 text-sm text-text">
        {lines.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-2">
            <dt>{label}</dt>
            <dd className="m-0">{formatK(value)}</dd>
          </div>
        ))}
        <div className="flex justify-between gap-2 border-t border-border pt-1 font-semibold">
          <dt>{t("import.quote.total")}</dt>
          <dd className="m-0">{formatK(quote.total_ngwee)}</dd>
        </div>
      </dl>
      {quote.lead_time_days ? (
        <p className="m-0 text-sm text-text-2">
          {t("import.quote.leadTime", { days: quote.lead_time_days })}
        </p>
      ) : null}
      {quote.valid_until ? (
        <p className="m-0 text-sm text-text-2">
          {t("import.quote.validUntil", {
            date: quote.valid_until.slice(0, 10),
          })}
        </p>
      ) : null}
      {quote.partner_label ? (
        <p className="m-0 text-sm text-text-2">
          {t("import.quote.partner", { name: quote.partner_label })}
        </p>
      ) : null}
      {quote.notes ? <p className="m-0 text-sm text-text-2">{quote.notes}</p> : null}
      <p className="m-0 text-micro text-text-2">{t("import.estimateNotice")}</p>
    </div>
  );
}
