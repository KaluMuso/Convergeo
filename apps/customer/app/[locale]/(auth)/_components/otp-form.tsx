"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { OtpField } from "@vergeo/ui/src/otp-field";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { parseAuthError, parseRetryAfterFromResponse, RESEND_COOLDOWN_SECONDS } from "./auth-utils";
import { navigateAfterCustomerAuth } from "./post-auth-navigation";
import { ResendCountdown } from "./resend-countdown";

type OtpFormLabels = {
  ariaGroup: string;
  digitLabel: string;
  submit: string;
  loading: string;
  resend: string;
  resendIn: string;
  changePhone: string;
  wrongCode: string;
  expired: string;
  throttled: string;
  generic: string;
  sendFailed: string;
};

type OtpFormProps = {
  locale: string;
  phone: string;
  labels: OtpFormLabels;
  loginPath: string;
  defaultNextPath: string;
  nextParam?: string | null;
};

export function OtpForm({
  locale,
  phone,
  labels,
  loginPath,
  defaultNextPath,
  nextParam,
}: OtpFormProps) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleVerify = async (otpCode: string) => {
    if (otpCode.length !== 6 || loading) {
      return;
    }

    setErrorMessage(null);
    setLoading(true);

    try {
      const supabase = await getBrowserClient();
      const { error } = await supabase.auth.verifyOtp({
        phone,
        token: otpCode,
        type: "sms",
      });

      if (error) {
        const parsed = parseAuthError(error);
        if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setErrorMessage(labels.throttled.replace("{seconds}", String(parsed.retryAfterSeconds)));
        } else if (parsed.code === "wrong_code") {
          setErrorMessage(labels.wrongCode);
        } else if (parsed.code === "expired") {
          setErrorMessage(labels.expired);
        } else {
          setErrorMessage(labels.generic);
        }
        return;
      }

      await navigateAfterCustomerAuth({
        router,
        locale,
        nextParam,
        fallbackPath: defaultNextPath,
      });
    } catch (response) {
      if (response instanceof Response && response.status === 429) {
        let body: unknown;
        try {
          body = await response.json();
        } catch {
          body = undefined;
        }
        const retryAfter = parseRetryAfterFromResponse(response, body) ?? 60;
        setErrorMessage(labels.throttled.replace("{seconds}", String(retryAfter)));
        return;
      }
      setErrorMessage(labels.generic);
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setErrorMessage(null);
    const supabase = await getBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({ phone });

    if (error) {
      const parsed = parseAuthError(error);
      if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
        setErrorMessage(labels.throttled.replace("{seconds}", String(parsed.retryAfterSeconds)));
      } else {
        setErrorMessage(labels.sendFailed);
      }
      throw error;
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-3">
        <OtpField
          value={code}
          onChange={setCode}
          onComplete={(value) => {
            void handleVerify(value);
          }}
          disabled={loading}
          ariaLabel={labels.ariaGroup}
          getDigitAriaLabel={(index) =>
            labels.digitLabel.replace("{position}", String(index + 1)).replace("{total}", "6")
          }
        />
        {errorMessage ? (
          <p role="alert" className="text-center font-body text-sm text-danger">
            {errorMessage}
          </p>
        ) : null}
      </div>

      <Button
        type="button"
        size="lg"
        className="w-full"
        loading={loading}
        loadingLabel={labels.loading}
        disabled={code.length !== 6}
        onClick={() => {
          void handleVerify(code);
        }}
      >
        {labels.submit}
      </Button>

      <ResendCountdown
        cooldownSeconds={RESEND_COOLDOWN_SECONDS}
        onResend={handleResend}
        resendLabel={labels.resend}
        resendInLabel={labels.resendIn}
        loadingLabel={labels.loading}
      />

      <Link
        href={`/${locale}${loginPath}`}
        className="text-center font-body text-sm text-primary underline-offset-2 hover:underline"
      >
        {labels.changePhone}
      </Link>
    </div>
  );
}
