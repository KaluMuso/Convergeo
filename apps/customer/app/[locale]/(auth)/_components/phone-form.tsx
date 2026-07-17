"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  DEFAULT_COUNTRY_CODE,
  formatE164,
  isValidZambianMobile,
  normalizeNationalNumber,
  parseAuthError,
  parseRetryAfterFromResponse,
} from "./auth-utils";

type PhoneFormLabels = {
  countryCode: string;
  nationalNumber: string;
  phoneLabel: string;
  phoneHelp: string;
  phonePlaceholder: string;
  submit: string;
  loading: string;
  required: string;
  invalidPhone: string;
  sendFailed: string;
  throttled: string;
};

type PhoneFormProps = {
  locale: string;
  labels: PhoneFormLabels;
  otpPath: string;
  mode?: "login" | "signup";
};

export function PhoneForm({ locale, labels, otpPath, mode = "login" }: PhoneFormProps) {
  const router = useRouter();
  const [countryCode] = useState(DEFAULT_COUNTRY_CODE);
  const [nationalNumber, setNationalNumber] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
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

    const phone = formatE164(countryCode, nationalNumber);
    setLoading(true);

    try {
      const supabase = await getBrowserClient();
      const { error } = await supabase.auth.signInWithOtp({
        phone,
        options: {
          shouldCreateUser: mode === "signup",
        },
      });

      if (error) {
        const parsed = parseAuthError(error);
        if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setErrorMessage(labels.throttled.replace("{seconds}", String(parsed.retryAfterSeconds)));
        } else {
          setErrorMessage(labels.sendFailed);
        }
        return;
      }

      const params = new URLSearchParams({ phone });
      router.push(`/${locale}${otpPath}?${params.toString()}`);
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
      setErrorMessage(labels.sendFailed);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="flex w-full flex-col gap-4" onSubmit={(event) => void handleSubmit(event)}>
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
        {labels.submit}
      </Button>
    </form>
  );
}
