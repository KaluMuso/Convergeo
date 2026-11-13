"use client";

import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Textarea } from "@vergeo/ui/src/textarea";
import { useEffect, useId, useState, type FormEvent } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";
import { fetchStorefrontConfigClient } from "../../../../../lib/storefront-config";

/**
 * Review-step extras: "Have a coupon code?" and "Send as a gift". Each is a
 * closed disclosure until opened, shown only when its feature flag is on, and
 * only for prepaid checkouts (coupons and gifts are never cash on delivery).
 */
export type CouponLabels = {
  toggle: string;
  label: string;
  apply: string;
  applying: string;
  remove: string;
  /** "{code} applied: {amount} off" */
  applied: string;
  /** "Paid for by {who}" hints */
  paidByPlatform: string;
  paidByShop: string;
  prepaidOnly: string;
  errors: Record<string, string>;
};

export type GiftLabels = {
  toggle: string;
  intro: string;
  recipientName: string;
  recipientPhone: string;
  recipientPhoneHelp: string;
  message: string;
  messageHelp: string;
  consent: string;
  pickupNote: string;
  deliveryNote: string;
  privacyNote: string;
  save: string;
  saving: string;
  remove: string;
  /** "Gift for {name} ({phone})" */
  saved: string;
  prepaidOnly: string;
  errors: Record<string, string>;
};

export type CheckoutExtrasLabels = { coupon: CouponLabels; gift: GiftLabels };

export type CheckoutTotals = {
  subtotal_ngwee: number;
  delivery_fee_ngwee: number;
  discount_ngwee: number;
  total_ngwee: number;
  coupon_code?: string | null;
};

type Props = {
  locale: string;
  sessionId: string;
  accessToken: string;
  labels: CheckoutExtrasLabels;
  isCod: boolean;
  hasPickup: boolean;
  initialCouponCode?: string | null;
  initialDiscountNgwee?: number;
  onTotals: (totals: CheckoutTotals) => void;
};

function errorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const key = error.details.message_key;
    if (typeof key === "string") return key.split(".").pop() ?? "generic";
    if (error.code === "rate_limited") return "tooManyAttempts";
  }
  return "generic";
}

function fill(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (text, [key, value]) => text.split(`{${key}}`).join(value),
    template,
  );
}

export function CheckoutExtras({
  locale,
  sessionId,
  accessToken,
  labels,
  isCod,
  hasPickup,
  initialCouponCode,
  initialDiscountNgwee = 0,
  onTotals,
}: Props) {
  const [flags, setFlags] = useState<{ coupons: boolean; giftOrders: boolean }>({
    coupons: false,
    giftOrders: false,
  });
  useEffect(() => {
    let cancelled = false;
    void fetchStorefrontConfigClient().then((config) => {
      if (!cancelled) setFlags({ coupons: config.coupons, giftOrders: config.giftOrders });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const client = createApiClient({ baseUrl: getApiBaseUrl(), getToken: () => accessToken });
  if (!flags.coupons && !flags.giftOrders) return null;
  return (
    <div className="space-y-3">
      {flags.coupons ? (
        <CouponBox
          locale={locale}
          sessionId={sessionId}
          labels={labels.coupon}
          isCod={isCod}
          initialCode={initialCouponCode ?? null}
          initialDiscount={initialDiscountNgwee}
          request={client.request.bind(client)}
          onTotals={onTotals}
        />
      ) : null}
      {flags.giftOrders ? (
        <GiftBox
          sessionId={sessionId}
          labels={labels.gift}
          isCod={isCod}
          hasPickup={hasPickup}
          request={client.request.bind(client)}
        />
      ) : null}
    </div>
  );
}

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;

function CouponBox({
  locale,
  sessionId,
  labels,
  isCod,
  initialCode,
  initialDiscount,
  request,
  onTotals,
}: {
  locale: string;
  sessionId: string;
  labels: CouponLabels;
  isCod: boolean;
  initialCode: string | null;
  initialDiscount: number;
  request: Request;
  onTotals: (totals: CheckoutTotals) => void;
}) {
  const inputId = useId();
  const [code, setCode] = useState("");
  const [applied, setApplied] = useState<{
    code: string;
    discount: number;
    funder?: string;
  } | null>(
    initialCode && initialDiscount > 0 ? { code: initialCode, discount: initialDiscount } : null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const totals = await request<CheckoutTotals & { coupon_funder?: string }>(
        "/checkout/steps/coupon",
        { method: "POST", body: JSON.stringify({ session_id: sessionId, code: code.trim() }) },
      );
      setApplied({
        code: totals.coupon_code ?? code.trim().toUpperCase(),
        discount: totals.discount_ngwee,
        funder: totals.coupon_funder,
      });
      setCode("");
      onTotals(totals);
    } catch (caught) {
      setError(labels.errors[errorKey(caught)] ?? labels.errors.generic ?? "");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const totals = await request<CheckoutTotals>(
        `/checkout/steps/coupon?session_id=${encodeURIComponent(sessionId)}`,
        { method: "DELETE" },
      );
      setApplied(null);
      onTotals(totals);
    } catch (caught) {
      setError(labels.errors[errorKey(caught)] ?? labels.errors.generic ?? "");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="rounded-card border border-border bg-surface px-4 py-3" open={!!applied}>
      <summary className="cursor-pointer font-body text-sm font-semibold text-text">
        {labels.toggle}
      </summary>
      <div className="mt-3 space-y-3">
        {isCod ? (
          <p className="font-body text-sm text-text-2">{labels.prepaidOnly}</p>
        ) : applied ? (
          <div className="flex flex-wrap items-center justify-between gap-2" role="status">
            <div className="space-y-0.5">
              <p className="font-body text-sm font-semibold text-success">
                {fill(labels.applied, {
                  code: applied.code,
                  amount: formatK(applied.discount, { locale: `${locale}-ZM` }),
                })}
              </p>
              {applied.funder ? (
                <p className="font-body text-xs text-text-3">
                  {applied.funder === "vendor" ? labels.paidByShop : labels.paidByPlatform}
                </p>
              ) : null}
            </div>
            <Button
              variant="ghost"
              size="sm"
              loading={busy}
              loadingLabel={labels.applying}
              onClick={() => void remove()}
            >
              {labels.remove}
            </Button>
          </div>
        ) : (
          <form className="flex items-end gap-2" onSubmit={(event) => void apply(event)}>
            <FormField id={inputId} label={labels.label} className="min-w-0 flex-1">
              <Input
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                autoCapitalize="characters"
                autoComplete="off"
                maxLength={32}
              />
            </FormField>
            <Button type="submit" variant="secondary" loading={busy} loadingLabel={labels.applying}>
              {labels.apply}
            </Button>
          </form>
        )}
        {error ? (
          <p role="alert" className="font-body text-sm text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function GiftBox({
  sessionId,
  labels,
  isCod,
  hasPickup,
  request,
}: {
  sessionId: string;
  labels: GiftLabels;
  isCod: boolean;
  hasPickup: boolean;
  request: Request;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [saved, setSaved] = useState<{ name: string; phone: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (!agreed) {
      setError(labels.errors.consent ?? "");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await request<{ recipient_name: string; recipient_phone_masked: string }>(
        "/checkout/steps/gift",
        {
          method: "PUT",
          body: JSON.stringify({
            session_id: sessionId,
            recipient_name: name,
            recipient_phone: phone,
            message: message.trim() || null,
            recipient_agreed: agreed,
          }),
        },
      );
      setSaved({ name: result.recipient_name, phone: result.recipient_phone_masked });
    } catch (caught) {
      setError(labels.errors[errorKey(caught)] ?? labels.errors.generic ?? "");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await request(`/checkout/steps/gift?session_id=${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      });
      setSaved(null);
    } catch (caught) {
      setError(labels.errors[errorKey(caught)] ?? labels.errors.generic ?? "");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="rounded-card border border-border bg-surface px-4 py-3" open={!!saved}>
      <summary className="cursor-pointer font-body text-sm font-semibold text-text">
        {labels.toggle}
      </summary>
      <div className="mt-3 space-y-3">
        {isCod ? (
          <p className="font-body text-sm text-text-2">{labels.prepaidOnly}</p>
        ) : saved ? (
          <div className="flex flex-wrap items-center justify-between gap-2" role="status">
            <p className="font-body text-sm font-semibold text-success">
              {fill(labels.saved, { name: saved.name, phone: saved.phone })}
            </p>
            <Button
              variant="ghost"
              size="sm"
              loading={busy}
              loadingLabel={labels.saving}
              onClick={() => void remove()}
            >
              {labels.remove}
            </Button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={(event) => void save(event)}>
            <p className="font-body text-sm text-text-2">{labels.intro}</p>
            <p className="font-body text-xs text-text-3">
              {hasPickup ? labels.pickupNote : labels.deliveryNote}
            </p>
            <FormField label={labels.recipientName} required>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={80}
                autoComplete="off"
                required
              />
            </FormField>
            <FormField label={labels.recipientPhone} helpText={labels.recipientPhoneHelp} required>
              <Input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                inputMode="tel"
                autoComplete="off"
                required
              />
            </FormField>
            <FormField label={labels.message} helpText={labels.messageHelp}>
              <Textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                maxLength={200}
                rows={2}
              />
            </FormField>
            <Checkbox
              label={labels.consent}
              checked={agreed}
              onChange={(event) => setAgreed(event.target.checked)}
            />
            <p className="font-body text-xs text-text-3">{labels.privacyNote}</p>
            <Button type="submit" variant="secondary" loading={busy} loadingLabel={labels.saving}>
              {labels.save}
            </Button>
          </form>
        )}
        {error ? (
          <p role="alert" className="font-body text-sm text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </details>
  );
}
