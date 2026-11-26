"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { useSession } from "@vergeo/auth/use-session";
import { ApiError } from "@vergeo/config";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, FormField, Input, Select, Spinner } from "../../listings/new/_lib/ui";
import { createPayoutsClient } from "../_lib/payouts-client";

type PayoutMethodFormProps = {
  locale: string;
};

const RESEND_COOLDOWN_SECONDS = 60;

export function PayoutMethodForm({ locale }: PayoutMethodFormProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [msisdn, setMsisdn] = useState("");
  const [rail, setRail] = useState<"mtn" | "airtel" | "zamtel">("mtn");
  const [otp, setOtp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const payoutsClient = useMemo(() => createPayoutsClient(getToken), [getToken]);

  useEffect(() => {
    if (resendCooldown <= 0) {
      return;
    }
    const timer = window.setInterval(() => {
      setResendCooldown((current) => (current > 0 ? current - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [resendCooldown]);

  const handleSendCode = async () => {
    const email = session?.user?.email;
    if (!email) {
      setError(t("payouts.errors.reauthRequired"));
      return;
    }
    setSendingCode(true);
    setError(null);
    try {
      const supabase = await getBrowserClient();
      const { error: otpError } = await supabase.auth.signInWithOtp({
        email,
        options: { shouldCreateUser: false },
      });
      if (otpError) {
        setError(t("payouts.errors.otpSendFailed"));
        return;
      }
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
    } catch {
      setError(t("payouts.errors.otpSendFailed"));
    } finally {
      setSendingCode(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await payoutsClient.changeMethod({
        payout_msisdn: msisdn.trim(),
        payout_rail: rail,
        otp: otp.trim(),
        channel: "email",
      });
      setSuccess(t("payouts.method.success"));
      setOtp("");
    } catch (err) {
      if (err instanceof ApiError && err.code === "payout_method_name_mismatch") {
        setError(t("payouts.errors.nameMismatch"));
      } else if (err instanceof ApiError && err.code === "reauth_required") {
        setError(t("payouts.errors.reauthRequired"));
      } else if (err instanceof ApiError && err.code === "reauth_failed") {
        setError(t("payouts.errors.otpFailed"));
      } else {
        setError(t("payouts.errors.methodFailed"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (sessionLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("payouts.loading")} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <Link
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
          href={`/${locale}/payouts`}
        >
          {t("payouts.method.back")}
        </Link>
        <h1 className="font-display text-2xl font-semibold">{t("payouts.method.title")}</h1>
        <p className="text-sm text-text-2">{t("payouts.method.intro")}</p>
      </header>

      <div
        className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm text-text"
        role="status"
      >
        <p className="font-medium">{t("payouts.hold.noticeTitle")}</p>
        <p className="mt-1">{t("payouts.hold.noticeBody")}</p>
      </div>

      {error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
          {success}
        </p>
      ) : null}

      <form className="flex flex-col gap-4" onSubmit={(event) => void handleSubmit(event)}>
        <FormField label={t("payouts.method.msisdnLabel")} id="payout-msisdn">
          <Input
            inputMode="tel"
            placeholder={t("payouts.method.msisdnPlaceholder")}
            value={msisdn}
            onChange={(event) => setMsisdn(event.target.value)}
            required
          />
        </FormField>

        <FormField label={t("payouts.method.railLabel")} id="payout-rail">
          <Select
            value={rail}
            onChange={(event) => setRail(event.target.value as "mtn" | "airtel" | "zamtel")}
          >
            <option value="mtn">{t("payouts.method.rails.mtn")}</option>
            <option value="airtel">{t("payouts.method.rails.airtel")}</option>
            <option value="zamtel">{t("payouts.method.rails.zamtel")}</option>
          </Select>
        </FormField>

        <FormField label={t("payouts.method.otpLabel")} id="payout-otp">
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder={t("payouts.method.otpPlaceholder")}
            value={otp}
            onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))}
            required
          />
        </FormField>
        <p className="text-xs text-text-3">{t("payouts.method.otpHelp")}</p>
        <Button
          type="button"
          variant="secondary"
          disabled={sendingCode || resendCooldown > 0 || !session}
          loading={sendingCode}
          loadingLabel={t("payouts.method.sendingCode")}
          onClick={() => void handleSendCode()}
        >
          {resendCooldown > 0
            ? t("payouts.method.resendIn", { seconds: resendCooldown })
            : t("payouts.method.sendCode")}
        </Button>

        <Button
          disabled={submitting || !session}
          loading={submitting}
          loadingLabel={t("payouts.method.saving")}
          type="submit"
        >
          {t("payouts.method.submit")}
        </Button>
      </form>
    </div>
  );
}
