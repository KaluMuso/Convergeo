"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { parseAuthError } from "./auth-utils";

type Status = "idle" | "sending" | "sent" | "error";

/**
 * Password-reset request: emails a Supabase recovery link that lands on
 * `/[locale]/reset-password/confirm`. Delivery depends on the Supabase project's
 * Auth SMTP being configured. Always shows a neutral "if an account exists"
 * confirmation so the form never reveals whether an email is registered.
 */
export function ResetRequestForm({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError(t("errors.required"));
      return;
    }

    setStatus("sending");
    try {
      const supabase = await getBrowserClient();
      const redirectTo = `${window.location.origin}/${locale}/reset-password/confirm`;
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo,
      });
      if (resetError) {
        const parsed = parseAuthError(resetError);
        if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setError(t("errors.throttled", { seconds: parsed.retryAfterSeconds }));
        } else {
          setError(t("errors.generic"));
        }
        setStatus("error");
        return;
      }
      setStatus("sent");
    } catch {
      setError(t("errors.generic"));
      setStatus("error");
    }
  };

  if (status === "sent") {
    return (
      <div className="flex w-full flex-col gap-4">
        <header className="space-y-1.5 text-center">
          <h1 className="font-display text-h2 text-display-ink">{t("reset.requestTitle")}</h1>
        </header>
        <p role="status" className="text-center font-body text-sm text-text-2">
          {t("reset.requestSent", { email: email.trim() })}
        </p>
        <Link
          href={`/${locale}/login`}
          className="text-center font-body text-sm text-primary underline-offset-2 hover:underline"
        >
          {t("reset.backToLogin")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{t("reset.requestTitle")}</h1>
        <p className="font-body text-sm text-text-2">{t("reset.requestSubtitle")}</p>
      </header>

      <form className="flex w-full flex-col gap-4" onSubmit={(event) => void handleSubmit(event)}>
        <FormField label={t("reset.emailLabel")} required requiredMarker="*">
          <Input
            size="lg"
            type="email"
            autoComplete="email"
            value={email}
            error={Boolean(error)}
            onChange={(event) => setEmail(event.target.value)}
          />
        </FormField>

        {error ? (
          <p role="alert" className="font-body text-sm text-danger">
            {error}
          </p>
        ) : null}

        <Button
          type="submit"
          size="lg"
          className="w-full"
          loading={status === "sending"}
          loadingLabel={t("reset.requestSending")}
        >
          {t("reset.requestSubmit")}
        </Button>
      </form>

      <Link
        href={`/${locale}/login`}
        className="text-center font-body text-sm text-primary underline-offset-2 hover:underline"
      >
        {t("reset.backToLogin")}
      </Link>
    </div>
  );
}
