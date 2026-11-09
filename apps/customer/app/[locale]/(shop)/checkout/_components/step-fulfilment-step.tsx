"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Radio } from "@vergeo/ui/src/radio";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

import { ReservationCountdown } from "./reservation-countdown";

import type {
  CheckoutSession,
  CountdownLabels,
  FulfilmentGroupResult,
  FulfilmentStepLabels,
  FulfilmentTotals,
  GroupChoice,
} from "./step-fulfilment";

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

  const handleSubmit = async () => {
    setErrorMessage(null);
    const deliveryNeeded = choices.some((choice) => choice.fulfilment === "delivery");
    if (deliveryNeeded && !landmark.trim()) {
      setErrorMessage(labels.landmarkLabel);
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
          }),
        });
        addressId = address.id;
      }

      const response = await client.request<{
        subtotal_ngwee: number;
        delivery_fee_ngwee: number;
        total_ngwee: number;
        groups: FulfilmentGroupResult[];
      }>("/checkout/steps/fulfilment", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          address: deliveryNeeded ? { landmark: landmark.trim() } : undefined,
          groups: choices,
        }),
      });
      const nextTotals: FulfilmentTotals = {
        subtotal_ngwee: response.subtotal_ngwee,
        delivery_fee_ngwee: response.delivery_fee_ngwee,
        total_ngwee: response.total_ngwee,
        groups: response.groups ?? [],
        addressId,
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
        <p className="font-body text-xs text-text-3">{labels.mixedHint}</p>
      </div>

      {choices.some((choice) => choice.fulfilment === "delivery") ? (
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
            onChange={(event) => {
              setLandmark(event.target.value);
              setTotals(null);
            }}
          />
        </FormField>
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
                <Radio
                  name={`fulfilment-${group.vendor_id}`}
                  label={labels.delivery}
                  checked={fulfilment === "delivery"}
                  disabled={!group.delivery_eligible}
                  onChange={() => {
                    setGroupFulfilment(group.vendor_id, "delivery");
                  }}
                />
                <Radio
                  name={`fulfilment-${group.vendor_id}`}
                  label={labels.pickup}
                  checked={fulfilment === "pickup"}
                  onChange={() => {
                    setGroupFulfilment(group.vendor_id, "pickup");
                  }}
                />
              </div>

              {fulfilment === "pickup" && pickup ? (
                <div className="rounded-md bg-bg-2 px-3 py-2 text-sm text-text-2">
                  <p>{labels.pickupAt(pickup.landmark)}</p>
                  <p className="text-xs text-text-3">
                    {labels.pickupHours(formatHours(pickup.hours))}
                  </p>
                </div>
              ) : null}

              {fulfilment === "delivery" && !group.delivery_eligible ? (
                <p className="text-xs text-warning">{labels.outsideZone}</p>
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
