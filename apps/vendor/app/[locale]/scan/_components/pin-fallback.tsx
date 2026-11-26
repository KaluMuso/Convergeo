"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { formatOrderCode } from "../../_lib/order-code";
import { Button, FormField, Input } from "../../listings/new/_lib/ui";

import type { PickupReadyOrder } from "../_lib/pickup-client";
import type { FormEvent } from "react";

type PinFallbackProps = {
  disabled: boolean;
  isSubmitting: boolean;
  readyOrders: PickupReadyOrder[];
  readyOrdersLoading: boolean;
  onSubmit: (orderId: string, pin: string) => void;
  onUseCamera?: () => void;
  showCameraOption: boolean;
};

export function PinFallback({
  disabled,
  isSubmitting,
  readyOrders,
  readyOrdersLoading,
  onSubmit,
  onUseCamera,
  showCameraOption,
}: PinFallbackProps) {
  const t = useTranslations("vendor");
  const [orderId, setOrderId] = useState("");
  const [pin, setPin] = useState("");
  const [selectedId, setSelectedId] = useState("");

  const handleSubmit = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      const trimmedOrderId = (selectedId || orderId).trim();
      const trimmedPin = pin.trim();
      if (!trimmedOrderId || trimmedPin.length !== 6) {
        return;
      }
      onSubmit(trimmedOrderId, trimmedPin);
    },
    [onSubmit, orderId, pin, selectedId],
  );

  const pickupReady = readyOrders.filter((row) => row.fulfilment === "pickup");

  return (
    <form
      data-testid="scan-pin-fallback"
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}
    >
      <div>
        <h2 style={{ margin: "0 0 var(--sp-1)", fontSize: "var(--fs-h3)" }}>
          {t("scan.pin.heading")}
        </h2>
        <p style={{ margin: 0, color: "var(--text-2)", fontSize: "var(--fs-small)" }}>
          {t("scan.pin.intro")}
        </p>
      </div>

      {pickupReady.length > 0 ? (
        <FormField id="pickup-order-pick" label={t("scan.pin.pickOrderLabel")}>
          <select
            id="pickup-order-pick"
            value={selectedId}
            onChange={(event) => {
              setSelectedId(event.target.value);
              if (event.target.value) {
                setOrderId("");
              }
            }}
            disabled={disabled || isSubmitting}
            style={{
              minHeight: "2.75rem",
              width: "100%",
              borderRadius: "var(--r)",
              border: "1px solid var(--border)",
              padding: "0 var(--sp-3)",
              fontSize: "var(--fs-body)",
              background: "var(--surface)",
            }}
          >
            <option value="">{t("scan.pin.pickOrderPlaceholder")}</option>
            {pickupReady.map((row) => (
              <option key={row.id} value={row.id}>
                {t("scan.pin.pickOrderOption", {
                  code: formatOrderCode(row.id),
                  title: row.preview_title,
                })}
              </option>
            ))}
          </select>
        </FormField>
      ) : readyOrdersLoading ? (
        <p style={{ margin: 0, fontSize: "var(--fs-small)", color: "var(--text-3)" }}>
          {t("scan.pin.loadingReady")}
        </p>
      ) : null}

      <FormField id="pickup-order-id" label={t("scan.pin.orderIdLabel")}>
        <Input
          id="pickup-order-id"
          value={orderId}
          onChange={(event) => {
            setOrderId(event.target.value);
            if (event.target.value.trim()) {
              setSelectedId("");
            }
          }}
          placeholder={t("scan.pin.orderIdPlaceholder")}
          autoComplete="off"
          disabled={disabled || isSubmitting || Boolean(selectedId)}
          inputMode="text"
        />
      </FormField>

      <FormField id="pickup-pin" label={t("scan.pin.pinLabel")}>
        <Input
          id="pickup-pin"
          value={pin}
          onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder={t("scan.pin.pinPlaceholder")}
          autoComplete="one-time-code"
          disabled={disabled || isSubmitting}
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
        />
      </FormField>

      <Button
        type="submit"
        loading={isSubmitting}
        loadingLabel={t("scan.pin.submitting")}
        disabled={disabled || pin.length !== 6 || (!orderId.trim() && !selectedId)}
      >
        {t("scan.pin.submit")}
      </Button>

      {showCameraOption && onUseCamera ? (
        <Button
          type="button"
          variant="secondary"
          loading={false}
          loadingLabel={t("scan.pin.useCamera")}
          onClick={onUseCamera}
          disabled={isSubmitting}
        >
          {t("scan.pin.useCamera")}
        </Button>
      ) : null}
    </form>
  );
}
