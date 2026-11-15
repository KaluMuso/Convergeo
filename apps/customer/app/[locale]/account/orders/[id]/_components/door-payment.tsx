"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../../../lib/api-base-url";

import type { DoorPayment } from "../../_components/orders-api";

export type DoorPaymentLabels = {
  title: string;
  /** "Pay {amount} with mobile money when the rider is at your door." */
  intro: (amount: string) => string;
  waitingRider: string;
  payNow: string;
  sending: string;
  otherNumber: string;
  phoneLabel: string;
  phoneHelp: string;
  pending: string;
  checkStatus: string;
  checking: string;
  failed: string;
  attemptsLeft: (count: number) => string;
  noAttemptsLeft: string;
  paid: string;
  cash: (amount: string) => string;
  errors: {
    invalidPhone: string;
    operatorUnsupported: string;
    inFlight: string;
    generic: string;
  };
};

type DoorPaymentBlockProps = {
  orderId: string;
  accessToken: string;
  initial: DoorPayment;
  labels: DoorPaymentLabels;
};

const POLL_MS = 5_000;
const MAX_POLLS = 24; // ~2 minutes, the prompt's lifetime

function errorMessage(error: unknown, labels: DoorPaymentLabels["errors"]): string {
  if (!(error instanceof ApiError)) {
    return labels.generic;
  }
  switch (error.code) {
    case "door_payment_invalid_phone":
    case "validation_error":
      return labels.invalidPhone;
    case "door_payment_operator_unsupported":
      return labels.operatorUnsupported;
    case "door_payment_in_flight":
      return labels.inFlight;
    default:
      return labels.generic;
  }
}

/**
 * Pay at the door: "Pay now on your phone" once the rider is at the door.
 * The amount is the server's; the handover code appears (page refresh) only
 * after the API confirms the payment with Lenco — never on this screen's word.
 */
export function DoorPaymentBlock({ orderId, accessToken, initial, labels }: DoorPaymentBlockProps) {
  const router = useRouter();
  const [door, setDoor] = useState<DoorPayment>(initial);
  const [busy, setBusy] = useState<"send" | "poll" | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [showPhone, setShowPhone] = useState(false);
  const [phone, setPhone] = useState("");
  const [polls, setPolls] = useState(0);

  const call = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => accessToken });
      return client.request<DoorPayment>(path, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      });
    },
    [accessToken],
  );

  const apply = useCallback(
    (next: DoorPayment) => {
      setDoor(next);
      if (next.state === "paid" || next.state === "cash") {
        router.refresh(); // the handover code is now served by the delivery endpoint
      }
    },
    [router],
  );

  const send = useCallback(async () => {
    if (busy) {
      return;
    }
    setBusy("send");
    setError(undefined);
    try {
      const trimmed = phone.trim();
      apply(
        await call(
          `/account/orders/${orderId}/door-payment`,
          showPhone && trimmed ? { phone: trimmed } : {},
        ),
      );
      setPolls(0);
    } catch (caught) {
      setError(errorMessage(caught, labels.errors));
    } finally {
      setBusy(null);
    }
  }, [apply, busy, call, labels.errors, orderId, phone, showPhone]);

  const poll = useCallback(async () => {
    setBusy((current) => current ?? "poll");
    try {
      apply(await call(`/account/orders/${orderId}/door-payment/poll`));
    } catch {
      // Weak signal at the door: keep the last known state, try again later.
    } finally {
      setBusy((current) => (current === "poll" ? null : current));
      setPolls((count) => count + 1);
    }
  }, [apply, call, orderId]);

  useEffect(() => {
    if (door.state !== "pending" || polls >= MAX_POLLS) {
      return undefined;
    }
    const timer = window.setTimeout(() => void poll(), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [door.state, poll, polls]);

  if (!door.enabled || door.state === "not_applicable" || door.state === "not_at_door") {
    return null;
  }

  const amount = formatK(door.amount_ngwee);
  const attemptsLeft = Math.max(door.attempts_allowed - door.attempts_used, 0);

  return (
    <section
      aria-labelledby="door-payment-heading"
      aria-live="polite"
      className="space-y-3 rounded border border-border bg-surface p-4"
      data-testid="door-payment"
      data-state={door.state}
    >
      <h3 id="door-payment-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>

      {door.state === "paid" ? (
        <p className="text-sm font-medium text-display-ink">{labels.paid}</p>
      ) : null}
      {door.state === "cash" ? (
        <p className="text-sm text-display-ink">{labels.cash(amount)}</p>
      ) : null}
      {door.state === "awaiting_arrival" ? (
        <>
          <p className="text-sm text-text-2">{labels.intro(amount)}</p>
          <p className="text-sm text-text-2">{labels.waitingRider}</p>
        </>
      ) : null}

      {door.state === "pending" ? (
        <>
          <p className="text-sm text-display-ink">{labels.pending}</p>
          <Button
            type="button"
            variant="secondary"
            className="min-h-11 w-full"
            disabled={busy !== null}
            loading={busy === "poll"}
            loadingLabel={labels.checking}
            onClick={() => void poll()}
          >
            {labels.checkStatus}
          </Button>
        </>
      ) : null}

      {door.state === "awaiting_payment" || door.state === "failed" ? (
        <>
          <p className="text-sm text-text-2">
            {door.state === "failed" ? labels.failed : labels.intro(amount)}
          </p>
          {door.can_request ? (
            <>
              {showPhone ? (
                <label className="block space-y-1 text-sm">
                  <span className="font-medium text-display-ink">{labels.phoneLabel}</span>
                  <input
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    className="min-h-11 w-full rounded border border-border bg-surface px-3"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                  />
                  <span className="block text-xs text-text-2">{labels.phoneHelp}</span>
                </label>
              ) : (
                <button
                  type="button"
                  className="min-h-11 text-sm font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setShowPhone(true)}
                >
                  {labels.otherNumber}
                </button>
              )}
              <Button
                type="button"
                className="min-h-11 w-full"
                disabled={busy !== null}
                loading={busy === "send"}
                loadingLabel={labels.sending}
                onClick={() => void send()}
              >
                {labels.payNow}
              </Button>
              {door.attempts_used > 0 ? (
                <p className="text-xs text-text-2">{labels.attemptsLeft(attemptsLeft)}</p>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-text-2">{labels.noAttemptsLeft}</p>
          )}
        </>
      ) : null}

      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
