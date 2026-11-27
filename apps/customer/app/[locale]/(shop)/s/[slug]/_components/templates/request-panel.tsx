"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { glassClass } from "@vergeo/ui/src/glass";
import { useEffect, useMemo, useState } from "react";

import {
  RequestQuoteButton,
  type RequestQuoteLabels,
} from "../../../../_components/pdp/request-quote-button";
import { asRecord, attrString, vibeStyle, type Archetype } from "../../_lib/archetypes";
import {
  ARCHETYPE_FIELDS,
  buildRequestText,
  EMPTY_FIELDS,
  validateRequest,
  type RequestErrorKey,
  type RequestFields,
  type RequestTextLabels,
} from "../../_lib/request-text";

import { REQUEST_PANEL_ID, SELECT_OFFER_EVENT } from "./select-offer-button";

import type { ServicePackage } from "../service-packages-model";

export type RequestPanelLabels = {
  heading: string;
  cta: string;
  fix: string;
  chooseOffer: string;
  selectOffer: string;
  startDate: Record<Archetype, string>;
  endDate: string;
  time: string;
  guests: string;
  quantity: string;
  period: string;
  staff: string;
  anyStaff: string;
  timeOfDay: Record<string, string>;
  nightsOne: string;
  nightsMany: string;
  periods: Record<string, { one: string; many: string }>;
  errors: Record<RequestErrorKey, string>;
  noPaymentNote: string;
  dialogTitle: string;
};

type RequestPanelProps = {
  locale: string;
  serviceId: string;
  vendorName: string;
  archetype: Archetype;
  offers: ServicePackage[];
  staffNames: string[];
  labels: RequestPanelLabels;
  quoteLabels: RequestQuoteLabels;
};

const TIME_KEYS = ["any", "morning", "afternoon", "evening"] as const;

function inputClass(): string {
  return "min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm text-text";
}

/**
 * Booking request panel (docs/plan/service-type-templates.md, ST-6): collects the
 * archetype's booking fields, shows the chosen offer, and opens the existing request-quote
 * dialog prefilled with a localised summary plus the `package_id`. A request, never a
 * reservation or a payment (SP-1).
 */
export function ServiceRequestPanel({
  locale,
  serviceId,
  vendorName,
  archetype,
  offers,
  staffNames,
  labels,
  quoteLabels,
}: RequestPanelProps) {
  const [offerId, setOfferId] = useState<string>(offers.length === 1 ? (offers[0]?.id ?? "") : "");
  const [fields, setFields] = useState<RequestFields>(EMPTY_FIELDS);
  const [today, setToday] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const shown = ARCHETYPE_FIELDS[archetype];

  useEffect(() => {
    setToday(new Date().toISOString().slice(0, 10));
  }, []);

  useEffect(() => {
    const onSelect = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      if (offers.some((offer) => offer.id === id)) setOfferId(id);
    };
    window.addEventListener(SELECT_OFFER_EVENT, onSelect);
    return () => window.removeEventListener(SELECT_OFFER_EVENT, onSelect);
  }, [offers]);

  const offer = offers.find((item) => item.id === offerId) ?? null;
  const unit = attrString(asRecord(offer?.attributes), "unit") ?? "day";
  const set = <K extends keyof RequestFields>(key: K, value: RequestFields[K]) =>
    setFields((prev) => ({ ...prev, [key]: value }));

  const error = validateRequest(archetype, fields, {
    hasOffers: offers.length > 0,
    offerSelected: offer !== null,
    today: today || "0000-00-00",
  });

  const textLabels: RequestTextLabels = useMemo(
    () => ({
      offer: labels.selectOffer,
      startDate: labels.startDate,
      endDate: labels.endDate,
      time: labels.time,
      guests: labels.guests,
      quantity: labels.quantity,
      period: labels.period,
      staff: labels.staff,
      nightsOne: labels.nightsOne,
      nightsMany: labels.nightsMany,
      periods: labels.periods,
      timeOfDay: labels.timeOfDay,
    }),
    [labels],
  );

  const details = buildRequestText({
    archetype,
    fields,
    offerName: offer?.name ?? null,
    offerPrice: offer && offer.price_ngwee !== null ? formatK(offer.price_ngwee) : null,
    unit,
    labels: textLabels,
  });

  return (
    <section
      id={REQUEST_PANEL_ID}
      className={`flex flex-col gap-3 rounded-lg border border-border p-5 shadow-2 ${glassClass("card")}`}
      style={vibeStyle(archetype)}
      aria-labelledby="request-panel-heading"
      data-testid="request-panel"
    >
      <h2 id="request-panel-heading" className="m-0 font-display text-h2 text-display-ink">
        {labels.heading}
      </h2>

      {offers.length > 0 ? (
        <label className="flex flex-col gap-1 text-sm font-medium text-text">
          {labels.selectOffer}
          <select
            className={inputClass()}
            value={offerId}
            data-testid="request-offer"
            onChange={(event) => setOfferId(event.target.value)}
          >
            <option value="">{labels.chooseOffer}</option>
            {offers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
                {item.price_ngwee !== null ? ` · ${formatK(item.price_ngwee)}` : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        {shown.includes("startDate") ? (
          <label className="flex flex-col gap-1 text-sm font-medium text-text">
            {labels.startDate[archetype]}
            <input
              type="date"
              className={inputClass()}
              min={today || undefined}
              value={fields.startDate}
              data-testid="request-start"
              onChange={(event) => set("startDate", event.target.value)}
            />
          </label>
        ) : null}
        {shown.includes("endDate") ? (
          <label className="flex flex-col gap-1 text-sm font-medium text-text">
            {labels.endDate}
            <input
              type="date"
              className={inputClass()}
              min={fields.startDate || today || undefined}
              value={fields.endDate}
              data-testid="request-end"
              onChange={(event) => set("endDate", event.target.value)}
            />
          </label>
        ) : null}
        {shown.includes("time") ? (
          <label className="flex flex-col gap-1 text-sm font-medium text-text">
            {labels.time}
            <select
              className={inputClass()}
              value={fields.time}
              data-testid="request-time"
              onChange={(event) => set("time", event.target.value)}
            >
              {TIME_KEYS.map((key) => (
                <option key={key} value={key}>
                  {labels.timeOfDay[key]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {shown.includes("staff") && staffNames.length > 0 ? (
          <label className="flex flex-col gap-1 text-sm font-medium text-text">
            {labels.staff}
            <select
              className={inputClass()}
              value={fields.staff}
              data-testid="request-staff"
              onChange={(event) => set("staff", event.target.value)}
            >
              <option value="">{labels.anyStaff}</option>
              {staffNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {(["guests", "period", "quantity"] as const)
          .filter((key) => shown.includes(key))
          .map((key) => (
            <label key={key} className="flex flex-col gap-1 text-sm font-medium text-text">
              {labels[key]}
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={key === "quantity" ? 500 : 30}
                className={inputClass()}
                value={fields[key] || ""}
                data-testid={`request-${key}`}
                onChange={(event) =>
                  set(
                    key,
                    Math.min(
                      key === "quantity" ? 500 : 30,
                      Math.trunc(Number(event.target.value) || 0),
                    ),
                  )
                }
                onBlur={() => {
                  if (fields[key] < 1) set(key, 1);
                }}
              />
            </label>
          ))}
      </div>

      {showErrors && error ? (
        <p role="alert" className="m-0 text-sm font-medium text-danger" data-testid="request-error">
          {labels.errors[error]}
        </p>
      ) : null}

      {error ? (
        <Button
          type="button"
          variant="primary"
          className="w-full rounded-md text-sm font-semibold"
          loadingLabel={labels.cta}
          data-testid="request-cta-blocked"
          onClick={() => setShowErrors(true)}
        >
          {labels.cta}
        </Button>
      ) : (
        <RequestQuoteButton
          locale={locale}
          serviceId={serviceId}
          packageId={offer?.id}
          vendorName={vendorName}
          initialDetails={details}
          variant="primary"
          ctaTestId="request-cta"
          className="w-full rounded-md text-sm font-semibold"
          labels={{
            ...quoteLabels,
            cta: labels.cta,
            dialogTitle: offer
              ? labels.dialogTitle.replace("{name}", offer.name)
              : quoteLabels.dialogTitle,
          }}
        />
      )}
      <p className="m-0 text-xs text-text-3">{labels.noPaymentNote}</p>
    </section>
  );
}
