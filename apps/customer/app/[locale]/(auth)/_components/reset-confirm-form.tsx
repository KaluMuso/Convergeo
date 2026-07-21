"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

import { parseAuthError } from "./auth-utils";

type Ready = "checking" | "ready" | "invalid";
type Status = "idle" | "saving" | "done" | "error";

/**
 * Completes a Supabase password recovery. The emailed link redirects here with a
 * PKCE `?code=`; we exchange it for a recovery session (mirroring the OAuth flow
 * in login-shell), then let the user set a new password via `updateUser`.
 */
export function ResetConfirmForm({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const router = useRouter();
  const [ready, setReady] = useState<Ready>("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const establishSession = async () => {
      const supabase = await getBrowserClient();
      const code = new URLSearchParams(window.location.search).get("code");
      if (code) {
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
        setReady(exchangeError ? "invalid" : "ready");
        return;
      }
      // No code in the URL — fall back to any recovery session already established.
      const { data } = await supabase.auth.getSession();
      setReady(data.session ? "ready" : "invalid");
    };
    void establishSession();
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError(t("reset.invalidPassword"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("reset.mismatch"));
      return;
    }

    setStatus("saving");
    try {
      const supabase = await getBrowserClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        const parsed = parseAuthError(updateError);
        if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
          setError(t("errors.throttled", { seconds: parsed.retryAfterSeconds }));
        } else {
          setError(t("errors.generic"));
        }
        setStatus("error");
        return;
      }
      setStatus("done");
    } catch {
      setError(t("errors.generic"));
      setStatus("error");
    }
  };

  if (ready === "checking") {
    return (
      <p role="status" className="text-center font-body text-sm text-text-2">
        {t("reset.checking")}
      </p>
    );
  }

  if (ready === "invalid") {
    return (
      <div className="flex w-full flex-col gap-4">
        <header className="space-y-1.5 text-center">
          <h1 className="font-display text-h2 text-display-ink">{t("reset.confirmTitle")}</h1>
        </header>
        <p role="alert" className="text-center font-body text-sm text-danger">
          {t("reset.linkInvalid")}
        </p>
        <Link
          href={`/${locale}/reset-password`}
          className="text-center font-body text-sm text-primary underline-offset-2 hover:underline"
        >
          {t("reset.requestSubmit")}
        </Link>
      </div>
    );
  }

  if (status === "done") {
    return (
      <div className="flex w-full flex-col gap-4">
        <header className="space-y-1.5 text-center">
          <h1 className="font-display text-h2 text-display-ink">{t("reset.confirmTitle")}</h1>
        </header>
        <p role="status" className="text-center font-body text-sm text-text-2">
          {t("reset.confirmSuccess")}
        </p>
        <Button
          type="button"
          size="lg"
          className="w-full"
          loadingLabel={t("reset.goToLogin")}
          onClick={() => {
            router.push(`/${locale}/login`);
            router.refresh();
          }}
        >
          {t("reset.goToLogin")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{t("reset.confirmTitle")}</h1>
        <p className="font-body text-sm text-text-2">{t("reset.confirmSubtitle")}</p>
      </header>

      <form className="flex w-full flex-col gap-4" onSubmit={(event) => void handleSubmit(event)}>
        <FormField label={t("reset.newPasswordLabel")} required requiredMarker="*">
          <Input
            size="lg"
            type="password"
            autoComplete="new-password"
            value={password}
            error={Boolean(error)}
            onChange={(event) => setPassword(event.target.value)}
          />
        </FormField>

        <FormField label={t("reset.confirmPasswordLabel")} required requiredMarker="*">
          <Input
            size="lg"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            error={Boolean(error)}
            onChange={(event) => setConfirmPassword(event.target.value)}
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
          loading={status === "saving"}
          loadingLabel={t("reset.confirmSaving")}
        >
          {t("reset.confirmSubmit")}
        </Button>
      </form>
    </div>
  );
}
