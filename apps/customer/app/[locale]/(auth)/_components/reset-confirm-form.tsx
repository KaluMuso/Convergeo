"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { parseAuthError, parseRetryAfterFromResponse } from "./auth-utils";

type Ready = "checking" | "ready" | "invalid";
type Status = "idle" | "saving" | "done" | "error";
type RecoverySession = { userId: string; sessionId: string };

/**
 * Completes a Supabase password recovery. The emailed link redirects here with a
 * PKCE `?code=`; we exchange it for a recovery session (mirroring the OAuth flow
 * in login-shell), then bind password setup to the verified recovery session.
 */
export function ResetConfirmForm({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const router = useRouter();
  const [ready, setReady] = useState<Ready>("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const recoverySession = useRef<RecoverySession | null>(null);

  useEffect(() => {
    let active = true;
    const establishSession = async () => {
      try {
        const code = new URLSearchParams(window.location.search).get("code");
        if (!code) {
          if (active) setReady("invalid");
          return;
        }
        const supabase = await getBrowserClient();
        if (!active) return;
        // A valid OAuth/sign-in code also creates a session. Only a recovery
        // exchange may open this form; Supabase marks it with this auth event.
        let recoveryEventUserId: string | null = null;
        let recoveryEventAccessToken: string | null = null;
        const {
          data: { subscription },
        } = supabase.auth.onAuthStateChange((event, session) => {
          if (event === "PASSWORD_RECOVERY") {
            recoveryEventUserId = session?.user.id ?? null;
            recoveryEventAccessToken = session?.access_token ?? null;
          }
        });
        try {
          const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          const matchingSession =
            !exchangeError &&
            recoveryEventAccessToken &&
            data.session &&
            data.session.access_token === recoveryEventAccessToken &&
            data.session.user.id === recoveryEventUserId
              ? data.session
              : null;
          const { data: verified, error: claimsError } = matchingSession
            ? await supabase.auth.getClaims(matchingSession.access_token)
            : { data: null, error: null };
          const session =
            !claimsError &&
            matchingSession &&
            verified?.claims.sub === matchingSession.user.id &&
            verified.claims.session_id
              ? {
                  userId: matchingSession.user.id,
                  sessionId: verified.claims.session_id,
                }
              : null;
          if (active) {
            recoverySession.current = session;
            setReady(session ? "ready" : "invalid");
          }
        } finally {
          subscription.unsubscribe();
        }
      } catch {
        if (active) setReady("invalid");
      }
    };
    void establishSession();
    return () => {
      active = false;
    };
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
      const { data } = await supabase.auth.getSession();
      const expected = recoverySession.current;
      const accessToken = data.session?.access_token;
      const { data: current, error: claimsError } = accessToken
        ? await supabase.auth.getClaims(accessToken)
        : { data: null, error: null };
      if (
        !expected ||
        claimsError ||
        current?.claims.sub !== expected.userId ||
        current.claims.session_id !== expected.sessionId ||
        !accessToken
      ) {
        setReady("invalid");
        return;
      }
      // updateUser rereads shared storage; another tab may switch accounts after
      // the check. The explicit bearer fixes the target of this request.
      const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
      const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
      if (!supabaseUrl || !anonKey) throw new Error("Missing Supabase config");
      const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/user`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          apikey: anonKey,
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const parsed = parseAuthError({
          status: response.status,
          retryAfter: parseRetryAfterFromResponse(response),
        });
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
