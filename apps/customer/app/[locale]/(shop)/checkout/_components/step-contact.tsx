"use client";

import { createBrowserClient } from "@vergeo/auth/browser-client";
import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { OtpField } from "@vergeo/ui/src/otp-field";
import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  DEFAULT_COUNTRY_CODE,
  formatE164,
  isValidZambianMobile,
  normalizeNationalNumber,
  parseAuthError,
  RESEND_COOLDOWN_SECONDS,
} from "../../../(auth)/_components/auth-utils";
import { ResendCountdown } from "../../../(auth)/_components/resend-countdown";

export type ContactStepLabels = {
  title: string;
  subtitle: string;
  phoneLabel: string;
  phoneHelp: string;
  phonePlaceholder: string;
  countryCode: string;
  nationalNumber: string;
  sendOtp: string;
  verifyOtp: string;
  otpAria: string;
  otpDigit: (position: number, total: number) => string;
  resend: string;
  resendIn: (seconds: number) => string;
  changePhone: string;
  loading: string;
  required: string;
  invalidPhone: string;
  sendFailed: string;
  wrongCode: string;
  expired: string;
  throttled: (seconds: number) => string;
  generic: string;
  skippedLoggedIn: string;
};

type StepContactProps = {
  labels: ContactStepLabels;
  onComplete: () => void;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function StepContact({ labels, onComplete }: StepContactProps) {
  const { session, loading: sessionLoading } = useSession();
  const [phase, setPhase] = useState<"phone" | "otp">("phone");
  const [countryCode] = useState(DEFAULT_COUNTRY_CODE);
  const [nationalNumber, setNationalNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const skippedRef = useRef(false);

  const completeContactStep = async (accessToken: string, contactPhone?: string) => {
    const client = createApiClient({
      baseUrl: getApiBaseUrl(),
      getToken: () => accessToken,
    });
    await client.request("/checkout/steps/contact", {
      method: "POST",
      body: JSON.stringify(contactPhone ? { phone: contactPhone } : {}),
    });
    onComplete();
  };

  useEffect(() => {
    if (sessionLoading || !session?.access_token || skippedRef.current) {
      return;
    }
    skippedRef.current = true;
    void completeContactStep(session.access_token).catch(() => {
      setErrorMessage(labels.generic);
      skippedRef.current = false;
    });
  }, [session, sessionLoading, labels.generic, onComplete]);

  if (sessionLoading) {
    return (
      <p className="font-body text-sm text-text-3" aria-live="polite">
        {labels.loading}
      </p>
    );
  }

  if (session?.access_token) {
    return (
      <div className="space-y-2">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="font-body text-sm text-text-2">{labels.skippedLoggedIn}</p>
      </div>
    );
  }

  const handleSendOtp = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    if (!nationalNumber.trim()) {
      setErrorMessage(labels.required);
      return;
    }
    if (!isValidZambianMobile(nationalNumber)) {
      setErrorMessage(labels.invalidPhone);
      return;
    }

    const e164 = formatE164(countryCode, nationalNumber);
    setLoading(true);
    try {
      const supabase = createBrowserClient();
      const { error } = await supabase.auth.signInWithOtp({
        phone: e164,
        options: { shouldCreateUser: true },
      });
      if (error) {
        const parsed = parseAuthError(error);
        if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setErrorMessage(labels.throttled(parsed.retryAfterSeconds));
        } else {
          setErrorMessage(labels.sendFailed);
        }
        return;
      }
      setPhone(e164);
      setPhase("otp");
    } catch {
      setErrorMessage(labels.sendFailed);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (otpCode: string) => {
    if (otpCode.length !== 6 || loading) {
      return;
    }
    setErrorMessage(null);
    setLoading(true);
    try {
      const supabase = createBrowserClient();
      const { data, error } = await supabase.auth.verifyOtp({
        phone,
        token: otpCode,
        type: "sms",
      });
      if (error) {
        const parsed = parseAuthError(error);
        if (parsed.code === "wrong_code") {
          setErrorMessage(labels.wrongCode);
        } else if (parsed.code === "expired") {
          setErrorMessage(labels.expired);
        } else if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setErrorMessage(labels.throttled(parsed.retryAfterSeconds));
        } else {
          setErrorMessage(labels.generic);
        }
        return;
      }
      const token = data.session?.access_token;
      if (!token) {
        setErrorMessage(labels.generic);
        return;
      }
      await completeContactStep(token, phone);
    } catch {
      setErrorMessage(labels.generic);
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    const supabase = createBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({ phone });
    if (error) {
      throw error;
    }
  };

  if (phase === "phone") {
    return (
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
          <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
        </div>
        <form className="flex flex-col gap-4" onSubmit={(event) => void handleSendOtp(event)}>
          <FormField
            label={labels.phoneLabel}
            helpText={labels.phoneHelp}
            errorMessage={errorMessage ?? undefined}
            required
            requiredMarker="*"
          >
            <div className="flex gap-2">
              <Input
                size="lg"
                className="w-24 shrink-0 text-center font-mono"
                value={countryCode}
                readOnly
                aria-label={labels.countryCode}
              />
              <Input
                size="lg"
                className="min-w-0 flex-1 font-mono"
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder={labels.phonePlaceholder}
                aria-label={labels.nationalNumber}
                value={nationalNumber}
                error={Boolean(errorMessage)}
                onChange={(event) => {
                  setNationalNumber(normalizeNationalNumber(event.target.value));
                }}
              />
            </div>
          </FormField>
          <Button
            type="submit"
            size="lg"
            className="w-full"
            loading={loading}
            loadingLabel={labels.loading}
          >
            {labels.sendOtp}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-display text-h2 text-display-ink">{labels.title}</h2>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
      </div>
      <div className="flex flex-col gap-4">
        <OtpField
          value={code}
          onChange={setCode}
          onComplete={(value) => {
            void handleVerifyOtp(value);
          }}
          disabled={loading}
          ariaLabel={labels.otpAria}
          getDigitAriaLabel={(index) => labels.otpDigit(index + 1, 6)}
        />
        {errorMessage ? (
          <p role="alert" className="text-center font-body text-sm text-danger">
            {errorMessage}
          </p>
        ) : null}
        <Button
          type="button"
          size="lg"
          className="w-full"
          loading={loading}
          loadingLabel={labels.loading}
          disabled={code.length !== 6}
          onClick={() => {
            void handleVerifyOtp(code);
          }}
        >
          {labels.verifyOtp}
        </Button>
        <ResendCountdown
          cooldownSeconds={RESEND_COOLDOWN_SECONDS}
          onResend={handleResend}
          resendLabel={labels.resend}
          resendInLabel={labels.resendIn}
          loadingLabel={labels.loading}
        />
        <Button
          type="button"
          variant="ghost"
          size="md"
          className="w-full"
          loadingLabel={labels.loading}
          onClick={() => {
            setPhase("phone");
            setCode("");
            setErrorMessage(null);
          }}
        >
          {labels.changePhone}
        </Button>
      </div>
    </div>
  );
}
