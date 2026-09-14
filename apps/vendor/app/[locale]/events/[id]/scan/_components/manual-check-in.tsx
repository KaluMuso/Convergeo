"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, FormField, Input } from "../../../../listings/new/_lib/ui";

import type { FormEvent } from "react";

/**
 * Manual (PIN) fallback for the organiser event scanner.
 *
 * Deliberately event-namespaced (`event-scan-*` testids, `scan.eventCheckIn.*`
 * copy) and NOT shared with the order-pickup scanner: that one verifies an
 * order with `{orderId, pin}` against the pickup API, this one verifies a
 * ticket with `{ticketId, pin}` against `POST /tickets/verify`. The two carry
 * different identifiers, different authorization, and different semantics.
 *
 * The PIN is held in local component state only for as long as it takes to
 * submit, is cleared on every submit, and is never logged or persisted.
 *
 * An in-flight verification locks the fields with `readOnly`, never `disabled`.
 * A disabled control cannot hold focus, so disabling the field the operator is
 * standing in destroys that focus: the browser drops it to <body>, which on a
 * phone also closes the on-screen keyboard. `readOnly` refuses the edit and
 * keeps the focus, which is the only part that has to survive the request.
 */

/**
 * Same muted chrome the shared field styles give a disabled field, so a locked
 * field still reads as locked now that it is `readOnly` rather than `disabled`.
 * `:read-only` also matches a disabled input, so the two states stay identical.
 */
const READ_ONLY_WHILE_BUSY = "read-only:bg-bg-2 read-only:text-text-3";

type ManualCheckInProps = {
  disabled: boolean;
  isSubmitting: boolean;
  offline: boolean;
  onSubmit: (ticketId: string, pin: string) => void;
  onUseCamera?: () => void;
};

export function ManualCheckIn({
  disabled,
  isSubmitting,
  offline,
  onSubmit,
  onUseCamera,
}: ManualCheckInProps) {
  const t = useTranslations("vendor");
  const [ticketId, setTicketId] = useState("");
  const [pin, setPin] = useState("");

  const trimmedTicketId = ticketId.trim();
  const canSubmit = !disabled && !isSubmitting && trimmedTicketId.length > 0 && pin.length === 6;

  const handleSubmit = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      if (!canSubmit) {
        return;
      }
      onSubmit(trimmedTicketId, pin);
      // Single-use credential: never leave it sitting in the field between guests.
      setPin("");
    },
    [canSubmit, onSubmit, pin, trimmedTicketId],
  );

  return (
    <form
      data-testid="event-scan-manual-fallback"
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}
    >
      <div>
        <h2 style={{ margin: "0 0 var(--sp-1)", fontSize: "var(--fs-h3)" }}>
          {t("scan.eventCheckIn.manual.heading")}
        </h2>
        <p
          style={{
            margin: 0,
            color: "var(--text-2)",
            fontSize: "var(--fs-small)",
          }}
        >
          {t("scan.eventCheckIn.manual.intro")}
        </p>
      </div>

      <FormField id="event-scan-ticket-id" label={t("scan.eventCheckIn.manual.ticketIdLabel")}>
        <Input
          data-testid="event-scan-manual-ticket-id"
          value={ticketId}
          onChange={(event) => setTicketId(event.target.value)}
          placeholder={t("scan.eventCheckIn.manual.ticketIdPlaceholder")}
          autoComplete="off"
          disabled={disabled}
          readOnly={isSubmitting}
          aria-busy={isSubmitting || undefined}
          className={READ_ONLY_WHILE_BUSY}
          inputMode="text"
        />
      </FormField>

      <FormField id="event-scan-ticket-pin" label={t("scan.eventCheckIn.manual.pinLabel")}>
        <Input
          data-testid="event-scan-manual-pin"
          value={pin}
          onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder={t("scan.eventCheckIn.manual.pinPlaceholder")}
          autoComplete="off"
          disabled={disabled}
          readOnly={isSubmitting}
          aria-busy={isSubmitting || undefined}
          className={READ_ONLY_WHILE_BUSY}
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
        />
      </FormField>

      {offline ? (
        <p
          data-testid="event-scan-manual-offline"
          role="status"
          style={{
            margin: 0,
            color: "var(--text-2)",
            fontSize: "var(--fs-small)",
          }}
        >
          {t("scan.eventCheckIn.manual.offline")}
        </p>
      ) : null}

      <Button
        type="submit"
        data-testid="event-scan-manual-submit"
        loading={isSubmitting}
        loadingLabel={t("scan.eventCheckIn.manual.submitting")}
        disabled={!canSubmit}
      >
        {t("scan.eventCheckIn.manual.submit")}
      </Button>

      {onUseCamera ? (
        <Button
          type="button"
          data-testid="event-scan-switch-camera"
          variant="secondary"
          loading={false}
          loadingLabel={t("scan.eventCheckIn.manual.useCamera")}
          onClick={onUseCamera}
          disabled={isSubmitting}
        >
          {t("scan.eventCheckIn.manual.useCamera")}
        </Button>
      ) : null}
    </form>
  );
}
