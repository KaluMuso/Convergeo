"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { OtpField } from "@vergeo/ui/src/otp-field";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { parseAuthError, parseRetryAfterFromResponse, RESEND_COOLDOWN_SECONDS } from "./auth-utils";
import { navigateAfterPortalAuth } from "./post-auth-navigation";
import { ResendCountdown } from "./resend-countdown";

import type { AuthPortal } from "@vergeo/auth/portal";

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
  portal?: AuthPortal;
  defaultNextPath: string;
  nextParam?: string | null;
};

export function OtpForm({
  locale,
  phone,
  labels,
  loginPath,
  portal = "customer",
  defaultNextPath,
  nextParam,
}: OtpFormProps) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  /**
   * Single-flight lock for OTP verification.
   *
   * A `loading` STATE flag cannot do this job. Verification has two independent
   * triggers — OtpField auto-submits via `onComplete` the instant the sixth
   * digit lands, and the Verify button's `onClick` — and `setLoading(true)`
   * only takes effect on the next render commit. A second trigger firing before
   * that commit (a click arriving in the same tick as the auto-submit, which is
   * exactly what a fast client does) still reads `loading === false` from its
   * own render closure and fires a duplicate `verifyOtp` for one submission.
   * Run #68's Vendor OTP traces show two POSTs to /auth/v1/verify for a single
   * code; the second necessarily races the first for an already-spent OTP.
   *
   * A ref mutation is synchronous and immediately visible to every subsequent
   * call in the same tick, so acquiring it before the first `await` closes the
   * window. This is the same guarantee OtpField already gives its own
   * `onComplete` via `completedRef` — the form just never applied it here.
   */
  const verifyingRef = useRef(false);

  const handleVerify = async (otpCode: string) => {
    // Acquire synchronously, before any await, or the guard is not a guard.
    if (otpCode.length !== 6 || verifyingRef.current) {
      return;
    }
    verifyingRef.current = true;

    setErrorMessage(null);
    setLoading(true);

    // Distinguishes "failed before the code was accepted" (recoverable — re-arm
    // submission) from "failed after it was accepted" (the OTP is spent, so
    // re-arming could only ever fire a second, doomed verifyOtp).
    let codeAccepted = false;

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
        // Recoverable: the user must be able to correct and resubmit the code.
        verifyingRef.current = false;
        setLoading(false);
        return;
      }

      codeAccepted = true;

      // Deliberately NOT released on success: the code is consumed and
      // navigation is in flight. Releasing here would re-arm submission during
      // the transition — the precise window this guard exists to close. The
      // component unmounts when navigation completes; `loading` stays true so
      // the field and button remain inert until it does.
      await navigateAfterPortalAuth({
        router,
        locale,
        portal,
        nextParam,
        fallbackPath: defaultNextPath,
      });
    } catch (response) {
      if (!codeAccepted) {
        verifyingRef.current = false;
      }
      setLoading(false);

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
