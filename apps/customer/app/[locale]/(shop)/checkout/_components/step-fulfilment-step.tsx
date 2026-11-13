"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import {
  type AddressType,
  type DeliveryPromise,
  LUSAKA_CUTOFF_HOUR,
  deliveryPromise,
  lusakaHour,
} from "../../../../../lib/delivery-estimate";

import { AreaPicker, type DeliveryArea } from "./area-picker";
import { ReservationCountdown } from "./reservation-countdown";

import type {
  CheckoutSession,
  CountdownLabels,
  FulfilmentGroupResult,
  FulfilmentGuideLabels,
  FulfilmentStepLabels,
  FulfilmentTotals,
  GroupChoice,
} from "./step-fulfilment";

type ApiPromise = {
  day: DeliveryPromise["day"];
  date: string;
  window_start: string;
  window_end: string;
};

/** "12:00–14:30 today" style copy; null when the labels predate the promise keys. */
export function promiseCopy(
  promise: DeliveryPromise,
  guide: FulfilmentGuideLabels | undefined,
  formatDate: (isoDate: string) => string,
): string | null {
  const template =
    promise.day === "today"
      ? guide?.promiseTodayTemplate
      : promise.day === "tomorrow"
        ? guide?.promiseTomorrowTemplate
        : guide?.promiseLaterTemplate;
  if (!template) return null;
  return template
    .replace("{start}", promise.windowStart)
    .replace("{end}", promise.windowEnd)
    .replace("{date}", formatDate(promise.date));
}

type StepFulfilmentProps = {
  locale: string;
  session: CheckoutSession;
  accessToken: string;
  labels: FulfilmentStepLabels;
  countdownLabels: CountdownLabels;
  reservationExpiredMessage: string;
  cartPath: string;
  onComplete?: (totals: FulfilmentTotals) => void;
};

function formatHours(hours: Record<string, unknown>): string {
  const entries = Object.entries(hours);
  if (entries.length === 0) {
    return "—";
  }
  return entries.map(([day, value]) => `${day}: ${String(value)}`).join(", ");
}

export function StepFulfilment({
  locale,
  session,
  accessToken,
  labels,
  countdownLabels,
  reservationExpiredMessage,
  cartPath,
  onComplete,
}: StepFulfilmentProps) {
  const router = useRouter();
  const [landmark, setLandmark] = useState("");
  const [areaSlug, setAreaSlug] = useState<string | null>(null);
  const [addressType, setAddressType] = useState<AddressType>("home");
  // undefined = not loaded yet; null = failed (the landmark still prices delivery).
  const [areas, setAreas] = useState<DeliveryArea[] | null | undefined>(undefined);
  const [serverPromise, setServerPromise] = useState<DeliveryPromise | null>(null);
  const [choices, setChoices] = useState<GroupChoice[]>(
    session.vendor_groups.map((group) => ({
      vendor_id: group.vendor_id,
      fulfilment: group.delivery_eligible ? "delivery" : "pickup",
    })),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [totals, setTotals] = useState<{
    subtotal_ngwee: number;
    delivery_fee_ngwee: number;
    total_ngwee: number;
  } | null>(null);

  const handleExpired = useCallback(() => {
    router.push(`${cartPath}?notice=reservation_expired`);
  }, [cartPath, router]);

  const setGroupFulfilment = (vendorId: string, fulfilment: "delivery" | "pickup") => {
    setChoices((current) =>
      current.map((choice) => (choice.vendor_id === vendorId ? { ...choice, fulfilment } : choice)),
    );
    setTotals(null);
  };

  const deliveryWanted = choices.some((choice) => choice.fulfilment === "delivery");
  const areaLabels = labels.area;
  useEffect(() => {
    if (!deliveryWanted || !areaLabels || areas !== undefined) return;
    let cancelled = false;
    void (async () => {
      try {
        const client = createApiClient({ baseUrl: getApiBaseUrl() });
        const response = await client.request<{ areas: DeliveryArea[] }>("/public/config/areas");
        if (!cancelled) setAreas(Array.isArray(response.areas) ? response.areas : null);
      } catch {
        if (!cancelled) setAreas(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [areaLabels, areas, deliveryWanted]);

  const handleSubmit = async () => {
    setErrorMessage(null);
    const deliveryNeeded = choices.some((choice) => choice.fulfilment === "delivery");
    if (deliveryNeeded && !landmark.trim()) {
      setErrorMessage(labels.guide?.landmarkRequired ?? labels.landmarkLabel);
      return;
    }

    setLoading(true);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => accessToken,
      });

      // Delivery orders require a persisted address_id on POST /orders.
      let addressId: string | null = null;
      if (deliveryNeeded) {
        const address = await client.request<{ id: string }>("/account/addresses", {
          method: "POST",
          body: JSON.stringify({
            landmark: landmark.trim(),
            label: labels.addressLabel,
            area_slug: areaSlug ?? undefined,
            address_type: addressType,
          }),
        });
        addressId = address.id;
      }

      const response = await client.request<{
        subtotal_ngwee: number;
        delivery_fee_ngwee: number;
        total_ngwee: number;
        groups: FulfilmentGroupResult[];
        delivery_promise?: ApiPromise | null;
      }>("/checkout/steps/fulfilment", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          address: deliveryNeeded
            ? {
                landmark: landmark.trim(),
                area_slug: areaSlug ?? undefined,
                address_type: addressType,
              }
            : undefined,
          groups: choices,
        }),
      });
      const apiPromise = response.delivery_promise;
      setServerPromise(
        apiPromise
          ? {
              day: apiPromise.day,
              date: apiPromise.date,
              windowStart: apiPromise.window_start,
              windowEnd: apiPromise.window_end,
            }
          : null,
      );
      const nextTotals: FulfilmentTotals = {
        subtotal_ngwee: response.subtotal_ngwee,
        delivery_fee_ngwee: response.delivery_fee_ngwee,
        total_ngwee: response.total_ngwee,
        groups: response.groups ?? [],
        addressId,
        landmark: deliveryNeeded ? landmark.trim() : null,
      };
      setTotals(nextTotals);
      onComplete?.(nextTotals);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "checkout.reservation_expired") {
          router.push(`${cartPath}?notice=reservation_expired`);
          return;
        }
        if (error.code === "checkout.outside_delivery_zone") {
          setErrorMessage(labels.outsideZone);
          return;
        }
      }
      setErrorMessage(labels.error);
    } finally {
      setLoading(false);
    }
  };

  const displaySubtotal = totals?.subtotal_ngwee ?? session.subtotal_ngwee;
  const displayDelivery = totals?.delivery_fee_ngwee ?? 0;
  const displayTotal = totals?.total_ngwee ?? session.subtotal_ngwee;
  const guide = labels.guide;
  const deliverySelected = choices.some((choice) => choice.fulfilment === "delivery");
  const hasMadeToOrder = session.vendor_groups.some((group) =>
    group.items.some((item) => item.fulfilment_mode === "made_to_order"),
  );
  // Lusaka clock, read once per render; the copy is advisory (vendor confirms dispatch).
  const afterCutoff = lusakaHour(new Date()) >= LUSAKA_CUTOFF_HOUR;
  const promise = serverPromise ?? deliveryPromise(new Date(), addressType);
  const promiseLine = deliverySelected
    ? promiseCopy(promise, guide, (iso) =>
        new Intl.DateTimeFormat(`${locale}-ZM`, {
          weekday: "long",
          day: "numeric",
          month: "long",
          timeZone: "UTC",
        }).format(new Date(`${iso}T00:00:00Z`)),
      )
    : null;

  return (
    <div className="space-y-5">
      <ReservationCountdown
        expiresAt={session.expires_at}
        label={countdownLabels.label}
        expiredLabel={countdownLabels.expired}
        ariaLiveLabel={countdownLabels.ariaLive}
        onExpired={handleExpired}
      />

      <div className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
        <p className="font-body text-xs text-text-3">{guide?.groupHint ?? labels.mixedHint}</p>
      </div>

      {guide ? (
        <div
          className="space-y-1 rounded-card border border-border bg-bg-2 px-4 py-3"
          data-testid="checkout-dispatch-cutoff"
        >
          <p className="font-body text-sm font-semibold text-text">{guide.cutoffTitle}</p>
          <p className="font-body text-sm text-text-2">
            {afterCutoff ? guide.cutoffAfter : guide.cutoffBefore}
          </p>
          {promiseLine ? (
            <p className="font-body text-sm font-semibold text-text" data-testid="checkout-promise">
              {promiseLine}
            </p>
          ) : null}
          {hasMadeToOrder ? (
            <p className="font-body text-xs text-text-3">{guide.cutoffMadeToOrder}</p>
          ) : null}
        </div>
      ) : null}

      {deliverySelected ? (
        <div className="space-y-3">
          {areaLabels && areas !== undefined ? (
            <AreaPicker
              areas={areas}
              value={areaSlug}
              onChange={(slug) => {
                setAreaSlug(slug);
                setTotals(null);
                setServerPromise(null);
              }}
              addressType={addressType}
              onAddressTypeChange={(type) => {
                setAddressType(type);
                setTotals(null);
                setServerPromise(null);
              }}
              labels={areaLabels}
            />
          ) : null}
          <FormField
            label={labels.landmarkLabel}
            helpText={labels.landmarkHelp}
            required
            requiredMarker="*"
          >
            <Input
              size="lg"
              value={landmark}
              placeholder={labels.landmarkPlaceholder}
              autoComplete="street-address"
              onChange={(event) => {
                setLandmark(event.target.value);
                setTotals(null);
              }}
            />
          </FormField>
          {guide ? (
            <div
              className="space-y-2 rounded-card border border-border bg-surface px-4 py-3"
              data-testid="checkout-landmark-tips"
            >
              <p className="font-body text-sm font-semibold text-text">{guide.tipsTitle}</p>
              <ul className="list-disc space-y-1 pl-5 font-body text-sm text-text-2">
                <li>{guide.tip1}</li>
                <li>{guide.tip2}</li>
                <li>{guide.tip3}</li>
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-4">
        {session.vendor_groups.map((group) => {
          const choice = choices.find((item) => item.vendor_id === group.vendor_id);
          const fulfilment = choice?.fulfilment ?? "pickup";
          const pickup = group.pickup_location;

          return (
            <section
              key={group.vendor_id}
              className="space-y-3 rounded-card border border-border bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-body text-base font-semibold text-text">{group.vendor_name}</h3>
                <span className="font-mono text-sm text-text-2">
                  {formatK(group.subtotal_ngwee, { locale: `${locale}-ZM` })}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <div>
                  <Radio
                    name={`fulfilment-${group.vendor_id}`}
                    label={labels.delivery}
                    checked={fulfilment === "delivery"}
                    disabled={!group.delivery_eligible}
                    aria-describedby={
                      guide ? `fulfilment-help-delivery-${group.vendor_id}` : undefined
                    }
                    onChange={() => {
                      setGroupFulfilment(group.vendor_id, "delivery");
                    }}
                  />
                  {guide ? (
                    <p
                      id={`fulfilment-help-delivery-${group.vendor_id}`}
                      className="pl-8 font-body text-xs text-text-3"
                    >
                      {guide.deliveryHelp}
                    </p>
                  ) : null}
                </div>
                <div>
                  <Radio
                    name={`fulfilment-${group.vendor_id}`}
                    label={labels.pickup}
                    checked={fulfilment === "pickup"}
                    aria-describedby={
                      guide ? `fulfilment-help-pickup-${group.vendor_id}` : undefined
                    }
                    onChange={() => {
                      setGroupFulfilment(group.vendor_id, "pickup");
                    }}
                  />
                  {guide ? (
                    <p
                      id={`fulfilment-help-pickup-${group.vendor_id}`}
                      className="pl-8 font-body text-xs text-text-3"
                    >
                      {guide.pickupHelp}
                    </p>
                  ) : null}
                </div>
              </div>

              {fulfilment === "pickup" && pickup ? (
                <div className="rounded-md bg-bg-2 px-3 py-2 text-sm text-text-2">
                  <p>{labels.pickupAt(pickup.landmark)}</p>
                  <p className="text-xs text-text-3">
                    {labels.pickupHours(formatHours(pickup.hours))}
                  </p>
                </div>
              ) : null}

              {!group.delivery_eligible ? (
                <p className="font-body text-xs text-text-2">{labels.outsideZone}</p>
              ) : null}
            </section>
          );
        })}
      </div>

      <div className="space-y-2 rounded-card border border-border bg-bg-2 px-4 py-3 font-mono text-sm">
        <div className="flex justify-between">
          <span>{labels.subtotal}</span>
          <span>{formatK(displaySubtotal, { locale: `${locale}-ZM` })}</span>
        </div>
        <div className="flex justify-between">
          <span>{labels.deliveryFees}</span>
          <span>{formatK(displayDelivery, { locale: `${locale}-ZM` })}</span>
        </div>
        <div className="flex justify-between font-semibold text-text">
          <span>{labels.total}</span>
          <span>{formatK(displayTotal, { locale: `${locale}-ZM` })}</span>
        </div>
      </div>

      {errorMessage ? (
        <p role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={loading}
        loadingLabel={labels.loading}
        onClick={() => {
          void handleSubmit();
        }}
      >
        {labels.continue}
      </Button>

      <p className="sr-only" aria-live="assertive">
        {reservationExpiredMessage}
      </p>
    </div>
  );
}
