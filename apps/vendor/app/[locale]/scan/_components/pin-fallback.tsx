"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, FormField, Input } from "../../listings/new/_lib/ui";

import type { FormEvent } from "react";

type PinFallbackProps = {
  disabled: boolean;
  isSubmitting: boolean;
  onSubmit: (orderId: string, pin: string) => void;
  onUseCamera?: () => void;
  showCameraOption: boolean;
};

export function PinFallback({
  disabled,
  isSubmitting,
  onSubmit,
  onUseCamera,
  showCameraOption,
}: PinFallbackProps) {
  const t = useTranslations("vendor");
  const [orderId, setOrderId] = useState("");
  const [pin, setPin] = useState("");

  const handleSubmit = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      const trimmedOrderId = orderId.trim();
      const trimmedPin = pin.trim();
      if (!trimmedOrderId || trimmedPin.length !== 6) {
        return;
      }
      onSubmit(trimmedOrderId, trimmedPin);
    },
    [onSubmit, orderId, pin],
  );

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

      <FormField id="pickup-order-id" label={t("scan.pin.orderIdLabel")}>
        <Input
          id="pickup-order-id"
          value={orderId}
          onChange={(event) => setOrderId(event.target.value)}
          placeholder={t("scan.pin.orderIdPlaceholder")}
          autoComplete="off"
          disabled={disabled || isSubmitting}
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
        disabled={disabled || !orderId.trim() || pin.length !== 6}
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
